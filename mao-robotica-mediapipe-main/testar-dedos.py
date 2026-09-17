"""Exercita cada dedo usando a mesma calibração do rastreamento."""
import argparse
import logging
from pathlib import Path
import time

from servo_braco3d import HandController, load_calibration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--port', help='Porta serial do Arduino')
    mode.add_argument('--simulate', action='store_true')
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('calibracao.json'))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        calibration = load_calibration(args.config)
        with HandController(calibration, args.port, args.simulate) as controller:
            controller.update({name: True for name in calibration})
            time.sleep(1)
            for name in calibration:
                controller.update({name: False})
                time.sleep(1)
                controller.update({name: True})
                time.sleep(1)
        return 0
    except KeyboardInterrupt:
        return 0
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        logging.error('%s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
