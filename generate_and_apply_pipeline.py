import yaml
import subprocess
import re
import os

# Constantes para os nomes dos arquivos e recursos Tekton
CI_CONFIG_PATH = 'ci-config.yaml'
OUTPUT_PIPELINE = 'generated_pipeline.yaml'
OUTPUT_PIPELINERUN = 'generated_pipelinerun.yaml'
PIPELINE_NAME = 'auto-generated-pipeline'
PIPELINERUN_NAME = 'auto-generated-pipeline-run'
NAMESPACE = 'ci-cd-trustme'

# Diretório temporário para salvar as Tasks geradas
GENERATED_TASKS_DIR = 'generated-tasks'

def normalize_name(s):
    """
    Normaliza uma string para ser um nome de recurso Kubernetes/Tekton válido.
    """
    name = s.lower()
    name = re.sub(r'[^a-z0-9-]+', '-', name)
    name = re.sub(r'-+', '-', name)
    name = name.strip('-')
    return name[:63]

def main():
    # Garante que o diretório para tasks geradas exista
    os.makedirs(GENERATED_TASKS_DIR, exist_ok=True)

    try:
        with open(CI_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Erro: O arquivo '{CI_CONFIG_PATH}' não foi encontrado.")
        exit(1)

    # Lista para armazenar os nomes das Tasks geradas para o Pipeline
    generated_pipeline_tasks_info = []

    # 1. Geração e Aplicação das Tasks Tekton separadas
    print(f"Gerando e aplicando Tasks separadas em '{GENERATED_TASKS_DIR}'...")
    for step_config in config['task_steps']:
        task_tekton_name = normalize_name(step_config['name'])
        generated_pipeline_tasks_info.append({'name': task_tekton_name, 'runAfter': step_config.get('runAfter')})

        # Concatena todos os comandos em um único script
        all_commands = '\n'.join(step_config['commands'])
        script_content = f"""#!/bin/sh
apt-get update && apt-get install -y make || echo 'make already installed or could not install'
{all_commands}
"""

        # Define o único step para a Task Tekton
        step_spec = {
            'name': task_tekton_name,
            'image': step_config['image'],
            'script': script_content,
            'workingDir': '$(workspaces.shared-workspace.path)'
        }

        if 'environment' in step_config:
            env_vars = [{'name': k, 'value': v} for k, v in step_config['environment'].items()]
            step_spec['env'] = env_vars

        task_tekton = {
            'apiVersion': 'tekton.dev/v1',
            'kind': 'Task',
            'metadata': {'name': task_tekton_name, 'namespace': NAMESPACE},
            'spec': {
                'workspaces': [{'name': 'shared-workspace'}],
                'steps': [step_spec]  # Apenas um step por task
            }
        }

        task_output_path = os.path.join(GENERATED_TASKS_DIR, f"{task_tekton_name}-task.yaml")
        with open(task_output_path, 'w') as f:
            yaml.dump(task_tekton, f, sort_keys=False)
        print(f"Task '{task_tekton_name}' gerada em '{task_output_path}'")

        try:
            subprocess.run(['kubectl', 'apply', '-f', task_output_path], check=True, capture_output=True)
            print(f"Task '{task_tekton_name}' aplicada com sucesso.")
        except subprocess.CalledProcessError as e:
            print(f"Erro ao aplicar a Task '{task_tekton_name}': {e}")
            print(f"Detalhes do erro: {e.stderr.decode() if e.stderr else 'Nenhuma saída de erro capturada.'}")
            exit(1)

    # 2. Geração do Objeto Pipeline (generated_pipeline.yaml)
    pipeline = {
        'apiVersion': 'tekton.dev/v1',
        'kind': 'Pipeline',
        'metadata': {'name': PIPELINE_NAME, 'namespace': NAMESPACE},
        'spec': {
            'workspaces': [{'name': 'shared-workspace'}],
            'tasks': []
        }
    }

    for task_info in generated_pipeline_tasks_info:
        pipeline_task = {
            'name': task_info['name'],
            'taskRef': {'name': task_info['name']},
            'workspaces': [
                {
                    'name': 'shared-workspace',
                    'workspace': 'shared-workspace'
                }
            ]
        }
        if task_info.get('runAfter'):
            pipeline_task['runAfter'] = task_info['runAfter']

        pipeline['spec']['tasks'].append(pipeline_task)

    with open(OUTPUT_PIPELINE, 'w') as f:
        yaml.dump(pipeline, f, sort_keys=False)
    print(f"Pipeline '{PIPELINE_NAME}' gerado em '{OUTPUT_PIPELINE}'")

    try:
        subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINE], check=True, capture_output=True)
        print(f"Pipeline '{PIPELINE_NAME}' aplicado com sucesso no cluster.")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao aplicar o Pipeline '{PIPELINE_NAME}': {e}")
        print(f"Detalhes do erro: {e.stderr.decode() if e.stderr else 'Nenhuma saída de erro capturada.'}")
        exit(1)

    # 3. Geração do Objeto PipelineRun (generated_pipelinerun.yaml)
    pipelinerun = {
        'apiVersion': 'tekton.dev/v1',
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
                        'claimName': 'shared-workspace-pvc'
                    }
                }
            ],
            'taskRunTemplate': {
                'serviceAccountName': 'trustme-tekton-triggers-sa'
            }
        }
    }

    with open(OUTPUT_PIPELINERUN, 'w') as f:
        yaml.dump(pipelinerun, f, sort_keys=False)
    print(f"PipelineRun '{PIPELINERUN_NAME}' gerado em '{OUTPUT_PIPELINERUN}'")

    try:
        subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINERUN], check=True, capture_output=True)
        print(f"PipelineRun '{PIPELINERUN_NAME}' aplicado com sucesso no cluster, disparando a execução.")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao aplicar o PipelineRun '{PIPELINERUN_NAME}': {e}")
        print(f"Detalhes do erro: {e.stderr.decode() if e.stderr else 'Nenhuma saída de erro capturada.'}")
        exit(1)

if __name__ == '__main__':
    main()
