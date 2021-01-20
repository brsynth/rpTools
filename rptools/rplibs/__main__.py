#!/usr/bin/env python

from rptools.rplibs      import rpCache
from rptools.rplibs.Args import build_args_parser
import logging


def gen_cache(outdir, logger):
    rpCache.generate_cache(outdir, logger)


def _cli():
    parser = build_args_parser()
    args  = parser.parse_args()

    # Create logger
    logger = logging.getLogger('rptools - rplibs')
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
            '%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, args.log.upper()))

    if args.cache_dir:
        print("rpCache is going to be generated into " + args.cache_dir)
        gen_cache(args.cache_dir, logger)


if __name__ == '__main__':
    _cli()
