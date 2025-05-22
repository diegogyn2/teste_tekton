import yaml
import subprocess
import re

CI_CONFIG_PATH = 'ci-config.yaml'
OUTPUT_PIPELINE = 'generated_pipeline.yaml'
OUTPUT_PIPELINERUN = 'generated_pipelinerun.yaml'
PIPELINE_NAME = 'auto-generated-pipeline'
PIPELINERUN_NAME = 'auto-generated-pipeline-run'
NAMESPACE = 'ci-cd-trustme'

def normalize_step_name(command):
    name = command.lower()
    name = re.sub(r'[^a-z0-9-]+', '-', name)
    name = re.sub(r'-+', '-', name)
    name = name.strip('-')
    return name[:63]

def main():
    # Carrega o config
    with open(CI_CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    # Gera o Pipeline
    pipeline = {
        'apiVersion': 'tekton.dev/v1',
        'kind': 'Pipeline',
        'metadata': {'name': PIPELINE_NAME},
        'spec': {
            'workspaces': [{'name': 'shared-workspace'}],
            'tasks': []
        }
    }

    for step in config['steps']:
        task = {
            'name': step['name'],
            'taskSpec': {
                'workspaces': [{'name': 'shared-workspace'}],
                'steps': []
            }
        }
        # Adiciona runAfter se existir
        if 'runAfter' in step:
            task['runAfter'] = step['runAfter']

        # Adiciona comandos como steps
        for command in step['commands']:
            step_name = normalize_step_name(command)
            step_spec = {
                'name': step_name,
                'image': step['image'],
                'script': f"#!/bin/sh\n{command}"
            }

            # Adiciona variáveis de ambiente, se houver
            if 'environment' in step:
                env_vars = [{'name': k, 'value': v} for k, v in step['environment'].items()]
                step_spec['env'] = env_vars

            task['taskSpec']['steps'].append(step_spec)

        pipeline['spec']['tasks'].append(task)

    # Salva o pipeline
    with open(OUTPUT_PIPELINE, 'w') as f:
        yaml.dump(pipeline, f, sort_keys=False)

    # Aplica o pipeline no cluster
    subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINE], check=True)

    # Gera o PipelineRun referenciando o PVC já criado
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
            ]
        }
    }

    # Salva o PipelineRun
    with open(OUTPUT_PIPELINERUN, 'w') as f:
        yaml.dump(pipelinerun, f, sort_keys=False)

    # Aplica o PipelineRun para disparar a execução
    subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINERUN], check=True)


if __name__ == '__main__':
    main()
