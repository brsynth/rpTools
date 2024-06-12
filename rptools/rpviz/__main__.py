#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""CLI for generating the JSON file expected by the pathway visualiser."""
 
__author__ = 'Thomas Duigou'
__license__ = 'MIT'


import os
import sys
import json
import logging
import tarfile
import argparse
import tempfile

from pathlib import Path

from rptools.rpviz.utils import annotate_cofactors, annotate_chemical_svg, get_autonomous_html, parse_all_pathways
from rptools.rpviz.Viewer import Viewer


def __build_arg_parser(prog='python -m rpviz.cli'):
    desc = 'Converting SBML RP file.'

    parser = argparse.ArgumentParser(description=desc, prog=prog)
    parser.add_argument('input_rpSBMLs',
                        help='Input file containing rpSBML files in a tar archive or a folder.')
    parser.add_argument('output_folder',
                        help='Output folder to be used. If it does not exist, an attempt will be made to create it.'
                             'It the creation of the folder fails, IOError will be raised.')
    parser.add_argument('--debug', action='store_true',
                        help='Turn on debug instructions')
    parser.add_argument('--cofactor',
                        default=os.path.join(os.path.dirname(__file__), 'data', 'cofactor_inchi_201811.tsv'),
                        help='File listing structures to consider as cofactors.')
    parser.add_argument('--autonomous_html',
                        default=None,
                        help="Optional file path, if provided will output an autonomous HTML containing all "
                             "dependencies.")

    return parser


def __run(args):
    # Make out folder if needed
    if not os.path.isfile(args.output_folder):
        try:
            os.makedirs(args.output_folder, exist_ok=True)
        except IOError as e:
            raise e

    # Both folder and tar file are valid inputs
    input_path = Path(args.input_rpSBMLs)
    if input_path.exists():
        # Input is a folder
        if input_path.is_dir():
            input_files = list(input_path.glob('*.xml'))
            if not len(input_files):
                raise FileNotFoundError(
                    f'"{args.input_rpSBMLs}" sounds like a directory '
                    'but no rpSBML files (xml extension) has been find. '
                    'Exit. '
                    )
            # Parse
            network, pathways_info = parse_all_pathways(input_files=input_files)
        # Input is a tarfile
        elif input_path.is_file() and tarfile.is_tarfile(args.input_rpSBMLs):
            with tempfile.TemporaryDirectory() as tmp_folder:
                with tarfile.open(args.input_rpSBMLs, mode='r') as tar:
                    def is_within_directory(directory, target):
                        
                        abs_directory = os.path.abspath(directory)
                        abs_target = os.path.abspath(target)
                    
                        prefix = os.path.commonprefix([abs_directory, abs_target])
                        
                        return prefix == abs_directory
                    
                    def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                    
                        for member in tar.getmembers():
                            member_path = os.path.join(path, member.name)
                            if not is_within_directory(path, member_path):
                                raise Exception("Attempted Path Traversal in Tar File")
                    
                        tar.extractall(path, members, numeric_owner=numeric_owner) 
                        
                    
                    safe_extract(tar, path=tmp_folder)
                _ = list(Path(tmp_folder).glob('*.xml'))
                if not len(_):  # Possible if there is a root folder
                    _ = list(Path(tmp_folder).glob('*/*.xml'))
                # Removed tar "fork" files if any (name starts by ._)
                input_files = [item for item in _ if not item.name.startswith('._')]
                # Check if any file to parse
                if not len(input_files):
                    raise FileNotFoundError(
                        f'No rpSBML files found in "{args.input_rpSBMLs}" tarfile. Exit.'
                        )
                # Parse
                network, pathways_info = parse_all_pathways(input_files=input_files)
        # Input is something else
        else:
            raise NotImplementedError(
                f'Unable to handle input "{args.input_rpSBMLs}". Exit. '
            )
    else:
        raise FileNotFoundError(
            f'"{args.input_rpSBMLs}" not found. Exit'
        )

    # Add annotations
    network = annotate_cofactors(network, args.cofactor)  # Typical cofactors
    network = annotate_chemical_svg(network)  # SVGs depiction for chemical

    # Build the Viewer
    viewer = Viewer(out_folder=args.output_folder)
    viewer.copy_templates()

    # Write info extracted from rpSBMLs
    json_out_file = os.path.join(args.output_folder, 'network.json')
    with open(json_out_file, 'w') as ofh:
        ofh.write('network = ' + json.dumps(network, indent=4))
        ofh.write(os.linesep)
        ofh.write('pathways_info = ' + json.dumps(pathways_info, indent=4))
    
    # Write single HTML if requested
    if args.autonomous_html is not None:
        str_html = get_autonomous_html(args.output_folder)
        with open(args.autonomous_html, 'wb') as ofh:
            ofh.write(str_html)


def __cli():
    logging.basicConfig(stream=sys.stderr,
                        level=logging.WARNING,
                        datefmt='%d/%m/%Y %H:%M:%S',
                        format='%(asctime)s -- %(levelname)s -- %(message)s')
    parser = __build_arg_parser()
    args = parser.parse_args()
    __run(args)


if __name__ == '__main__':
    __cli()