import yaml
import subprocess
import re

CI_CONFIG_PATH = 'ci-config.yaml'
OUTPUT_PIPELINE = 'generated_pipeline.yaml'

def normalize_step_name(command):
    name = command.lower()
    name = re.sub(r'[^a-z0-9-]+', '-', name)
    name = re.sub(r'-+', '-', name)
    name = name.strip('-')
    return name[:63]

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
        step_name = normalize_step_name(command)
        task['taskSpec']['steps'].append({
            'name': step_name,
            'image': step['image'],
            'env': [{'name': k, 'value': v} for k, v in step.get('environment', {}).items()],
            'script': f"#!/bin/sh\n{command}"
        })
    
    pipeline['spec']['tasks'].append(task)

with open(OUTPUT_PIPELINE, 'w') as f:
    yaml.dump(pipeline, f)

# Aplica no cluster
subprocess.run(['kubectl', 'apply', '-f', OUTPUT_PIPELINE])