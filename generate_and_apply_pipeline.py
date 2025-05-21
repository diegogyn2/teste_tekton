import yaml
import subprocess

CI_CONFIG_PATH = 'ci-config.yaml'
OUTPUT_PIPELINE = 'generated_pipeline.yaml'

with open(CI_CONFIG_PATH) as f:
    config = yaml.safe_load(f)

pipeline = {
    'apiVersion': 'tekton.dev/v1',
    'kind': 'Pipeline',
    'metadata': {'name': 'auto-generated-pipeline'},
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
    
    if 'runAfter' in step:
        task['runAfter'] = step['runAfter']
    
    for command in step['commands']:
        task['taskSpec']['steps'].append({
            'name': command.replace(' ', '-').lower()[:20],
            'image': step['image'],
            'env': [{'name': k, 'value': v} for k, v in step.get('environment', {}).items()],
            'script': f"#!/bin/sh\n{command}"
        })
    
    pipeline['spec']['tasks'].append(task)

with open(OUTPUT_PIPELINE, 'w') as f:
    yaml.dump(pipeline, f)

# Aplica no cluster
subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINE])
