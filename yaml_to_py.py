#!/usr/bin/python3
####################################################
# Script to pass from a yaml file to a python dictionary
# Useful to pass from a kubernetes manifest to a python client input
##########################

import sys
import yaml
import json

DEFAULT_YAML_FILE = "manifests/templates/service_cxg.yaml"

def yaml_to_py(file):
    # Expects yaml file path, prints python dict
    print(file)

    with open(file, "r") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
        print(json.dumps(data, indent=2))

def py_to_yaml(dic):
    # Expects python dict, prints yaml file
    print(yaml.dump(dic))

def main():
    file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_YAML_FILE
    yaml_to_py(file)

if __name__ == '__main__':
    main()

