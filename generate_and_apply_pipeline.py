import yaml
import subprocess
import re

# Constantes para os nomes dos arquivos e recursos Tekton
CI_CONFIG_PATH = 'ci-config.yaml'
OUTPUT_PIPELINE = 'generated_pipeline.yaml'
OUTPUT_PIPELINERUN = 'generated_pipelinerun.yaml'
PIPELINE_NAME = 'auto-generated-pipeline'
PIPELINERUN_NAME = 'auto-generated-pipeline-run'
NAMESPACE = 'ci-cd-trustme' # Certifique-se de que este namespace existe no seu cluster

def normalize_step_name(command):
    """
    Normaliza o nome de um comando para ser um nome de step válido para o Kubernetes/Tekton.
    Remove caracteres especiais, substitui espaços por hífens e limita o tamanho.
    """
    name = command.lower()
    name = re.sub(r'[^a-z0-9-]+', '-', name) # Mantém apenas letras minúsculas, números e hífens
    name = re.sub(r'-+', '-', name)         # Consolida múltiplos hífens
    name = name.strip('-')                  # Remove hífens do início e fim
    return name[:63] # Limita o nome a 63 caracteres (padrão Kubernetes)

def main():
    # Carrega o arquivo de configuração de CI (ci-config.yaml)
    # Este arquivo DEVE estar no diretório 'repo' clonado pelo meta-pipeline.
    try:
        with open(CI_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Erro: O arquivo '{CI_CONFIG_PATH}' não foi encontrado. "
              "Certifique-se de que ele existe no diretório do repositório clonado pelo meta-pipeline.")
        exit(1)

    # --- 1. Geração do Objeto Pipeline (generated_pipeline.yaml) ---
    pipeline = {
        'apiVersion': 'tekton.dev/v1',
        'kind': 'Pipeline',
        'metadata': {'name': PIPELINE_NAME, 'namespace': NAMESPACE}, # Adicionado namespace para clareza
        'spec': {
            'workspaces': [{'name': 'shared-workspace'}], # Declara o workspace necessário para o Pipeline
            'tasks': []
        }
    }

    # Itera sobre os passos definidos no ci-config.yaml para criar as Tasks do Pipeline
    for step_config in config['steps']:
        # Cada "step" no ci-config.yaml se torna uma Task independente no Tekton Pipeline
        task = {
            'name': step_config['name'],
            'taskSpec': {
                'workspaces': [{'name': 'shared-workspace'}], # Declara o workspace necessário para a Task
                'steps': [] # Lista de steps (comandos) dentro desta Task
            }
        }
        # Adiciona a dependência 'runAfter' se especificada no ci-config.yaml
        if 'runAfter' in step_config:
            task['runAfter'] = step_config['runAfter']

        # Itera sobre os comandos dentro de cada passo para criar os Steps das Tasks
        for command in step_config['commands']:
            step_name = normalize_step_name(command)
            step_spec = {
                'name': step_name,
                'image': step_config['image'],
                'script': f"#!/bin/sh\n{command}", # O comando a ser executado
                # --- INÍCIO DA CORREÇÃO IMPORTANTE ---
                # Garante que o workspace seja montado dentro do pod de cada step
                'volumeMounts': [
                    {
                        'name': 'shared-workspace', # Nome do workspace declarado na Task
                        'mountPath': '/workspace'   # Caminho onde o workspace será montado no contêiner do step
                    }
                ],
                'workingDir': '/workspace' # Define o diretório de trabalho para o caminho do workspace montado
                # --- FIM DA CORREÇÃO IMPORTANTE ---
            }

            # Adiciona variáveis de ambiente, se houver, para o step
            if 'environment' in step_config:
                env_vars = [{'name': k, 'value': v} for k, v in step_config['environment'].items()]
                step_spec['env'] = env_vars

            task['taskSpec']['steps'].append(step_spec)

        pipeline['spec']['tasks'].append(task)

    # Salva o Pipeline gerado em um arquivo YAML
    with open(OUTPUT_PIPELINE, 'w') as f:
        yaml.dump(pipeline, f, sort_keys=False)

    print(f"Pipeline '{PIPELINE_NAME}' gerado em '{OUTPUT_PIPELINE}'")

    # Aplica o Pipeline no cluster Kubernetes
    try:
        subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINE], check=True)
        print(f"Pipeline '{PIPELINE_NAME}' aplicado com sucesso no cluster.")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao aplicar o Pipeline '{PIPELINE_NAME}': {e}")
        # A saída de erro (stderr) geralmente contém a mensagem útil do kubectl
        print(f"Detalhes do erro: {e.stderr.decode()}")
        exit(1)

    # --- 2. Geração do Objeto PipelineRun (generated_pipelinerun.yaml) ---
    pipelinerun = {
        'apiVersion': 'tekton.dev/v1', # Versão correta para PipelineRun
        'kind': 'PipelineRun',
        'metadata': {
            'name': PIPELINERUN_NAME,
            'namespace': NAMESPACE
        },
        'spec': {
            'pipelineRef': {'name': PIPELINE_NAME},
            'workspaces': [
                {
                    'name': 'shared-workspace',
                    'persistentVolumeClaim': {
                        'claimName': 'shared-workspace-pvc' # PVC que será usado pelo workspace
                    }
                }
            ],
            # Configuração do ServiceAccount para as TaskRuns geradas por este PipelineRun
            'taskRunTemplate': {
                'serviceAccountName': 'trustme-tekton-triggers-sa'
            }
        }
    }

    # Salva o PipelineRun gerado em um arquivo YAML
    with open(OUTPUT_PIPELINERUN, 'w') as f:
        yaml.dump(pipelinerun, f, sort_keys=False)

    print(f"PipelineRun '{PIPELINERUN_NAME}' gerado em '{OUTPUT_PIPELINERUN}'")

    # Aplica o PipelineRun para disparar a execução da pipeline gerada
    try:
        subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINERUN], check=True)
        print(f"PipelineRun '{PIPELINERUN_NAME}' aplicado com sucesso no cluster, disparando a execução.")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao aplicar o PipelineRun '{PIPELINERUN_NAME}': {e}")
        print(f"Detalhes do erro: {e.stderr.decode()}")
        exit(1)

if __name__ == '__main__':
    main()