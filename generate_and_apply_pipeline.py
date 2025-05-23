import yaml
import subprocess
import re
import os
import sys

# Constantes
CI_CONFIG_PATH = 'ci-config.yaml'
OUTPUT_PIPELINE = 'generated_pipeline.yaml'
OUTPUT_PIPELINERUN = 'generated_pipelinerun.yaml'
PIPELINE_NAME = 'auto-generated-pipeline'
PIPELINERUN_NAME = 'auto-generated-pipeline-run'
NAMESPACE = 'ci-cd-trustme'
GENERATED_TASKS_DIR = 'generated-tasks'

def normalize_name(s):
    name = s.lower()
    name = re.sub(r'[^a-z0-9-]+', '-', name)
    name = re.sub(r'-+', '-', name)
    return name.strip('-')[:63]

def main():
    os.makedirs(GENERATED_TASKS_DIR, exist_ok=True)

    # Determina o tipo de evento: pull_request ou merge_request
    event_type = os.getenv('EVENT_TYPE')
    if not event_type:
        print("Erro: variável de ambiente 'EVENT_TYPE' não definida. Use 'pull_request' ou 'merge_request'.")
        exit(1)
    
    try:
        with open(CI_CONFIG_PATH) as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"Erro: O arquivo '{CI_CONFIG_PATH}' não foi encontrado.")
        exit(1)

    # Seleção das tasks conforme o tipo de evento
    if event_type == 'pull_request':
        selected_steps = [step for step in config['task_steps'] if step['name'] == 'validate']
    elif event_type == 'merge_request':
        selected_steps = [step for step in config['task_steps'] if step['name'] in ('build', 'deploy')]
    else:
        print(f"Erro: Tipo de evento '{event_type}' não reconhecido.")
        exit(1)

    if not selected_steps:
        print(f"Nenhuma task configurada para o tipo de evento '{event_type}'.")
        exit(1)

    generated_pipeline_tasks_info = []

    print(f"Gerando e aplicando Tasks para evento: '{event_type}'...")

    for step_config in selected_steps:
        task_tekton_name = normalize_name(step_config['name'])
        generated_pipeline_tasks_info.append({
            'name': task_tekton_name,
            'runAfter': step_config.get('runAfter')
        })

        task_tekton = {
            'apiVersion': 'tekton.dev/v1',
            'kind': 'Task',
            'metadata': {'name': task_tekton_name, 'namespace': NAMESPACE},
            'spec': {'workspaces': [{'name': 'shared-workspace'}], 'steps': []}
        }

        script_lines = [
            "#!/bin/sh",
            "apt-get update && apt-get install -y make || echo 'make already installed or could not install'"
        ] + step_config['commands']

        step_spec = {
            'name': normalize_name(step_config['name']),
            'image': step_config['image'],
            'script': "\n".join(script_lines),
            'workingDir': '$(workspaces.shared-workspace.path)/repo'
        }

        if 'environment' in step_config:
            env_vars = [{'name': k, 'value': v} for k, v in step_config['environment'].items()]
            step_spec['env'] = env_vars

        task_tekton['spec']['steps'].append(step_spec)

        task_output_path = os.path.join(GENERATED_TASKS_DIR, f"{task_tekton_name}-task.yaml")
        with open(task_output_path, 'w') as f:
            yaml.dump(task_tekton, f, sort_keys=False)
        
        print(f"Task '{task_tekton_name}' gerada em '{task_output_path}'")

        try:
            subprocess.run(['kubectl', 'apply', '-f', task_output_path], check=True, capture_output=True)
            print(f"Task '{task_tekton_name}' aplicada com sucesso.")
        except subprocess.CalledProcessError as e:
            print(f"Erro ao aplicar a Task '{task_tekton_name}': {e.stderr.decode()}")
            exit(1)

    # Geração do Pipeline
    pipeline = {
        'apiVersion': 'tekton.dev/v1',
        'kind': 'Pipeline',
        'metadata': {'name': PIPELINE_NAME, 'namespace': NAMESPACE},
        'spec': {'workspaces': [{'name': 'shared-workspace'}], 'tasks': []}
    }

    for task_info in generated_pipeline_tasks_info:
        pipeline_task = {
            'name': task_info['name'],
            'taskRef': {'name': task_info['name']},
            'workspaces': [{'name': 'shared-workspace', 'workspace': 'shared-workspace'}]
        }
        if task_info.get('runAfter'):
            pipeline_task['runAfter'] = task_info['runAfter']
        pipeline['spec']['tasks'].append(pipeline_task)

    with open(OUTPUT_PIPELINE, 'w') as f:
        yaml.dump(pipeline, f, sort_keys=False)
    print(f"Pipeline '{PIPELINE_NAME}' gerado em '{OUTPUT_PIPELINE}'")

    try:
        subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINE], check=True, capture_output=True)
        print(f"Pipeline '{PIPELINE_NAME}' aplicado com sucesso.")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao aplicar o Pipeline: {e.stderr.decode()}")
        exit(1)

    # Geração do PipelineRun
    pipelinerun = {
        'apiVersion': 'tekton.dev/v1',
        'kind': 'PipelineRun',
        'metadata': {'name': PIPELINERUN_NAME, 'namespace': NAMESPACE},
        'spec': {
            'pipelineRef': {'name': PIPELINE_NAME},
            'workspaces': [{'name': 'shared-workspace', 'persistentVolumeClaim': {'claimName': 'shared-workspace-pvc'}}],
            'taskRunTemplate': {'serviceAccountName': 'trustme-tekton-triggers-sa'}
        }
    }

    with open(OUTPUT_PIPELINERUN, 'w') as f:
        yaml.dump(pipelinerun, f, sort_keys=False)
    print(f"PipelineRun '{PIPELINERUN_NAME}' gerado em '{OUTPUT_PIPELINERUN}'")

    try:
        subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINERUN], check=True, capture_output=True)
        print(f"PipelineRun '{PIPELINERUN_NAME}' aplicado e executado com sucesso.")
    except subprocess.CalledProcessError as e:
        print(f"Erro ao aplicar o PipelineRun: {e.stderr.decode()}")
        exit(1)

if __name__ == '__main__':
    main()
