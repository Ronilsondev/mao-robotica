"""Rastreamento de uma mão e controle dos servos via Firmata."""
import argparse
from contextlib import ExitStack
import logging
import os
from pathlib import Path
import time

from gestos import GestureTracker, demo_landmarks
from servo_braco3d import HandController, load_calibration


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--camera', type=int, default=0, help='Índice da câmera (padrão: 0)')
    result.add_argument('--port', help='Porta do Arduino, por exemplo /dev/ttyUSB0 ou COM3')
    result.add_argument('--simulate', action='store_true', help='Usa câmera, sem conectar servos')
    result.add_argument('--demo', action='store_true', help='Gestos sintéticos, sem câmera nem Arduino')
    result.add_argument('--headless', action='store_true', help='Executa sem janela')
    result.add_argument('--frames', type=int, default=0, help='Encerra após N quadros; 0 = ilimitado')
    result.add_argument('--config', type=Path, default=Path(__file__).with_name('calibracao.json'))
    result.add_argument('--lost-action', choices=('hold', 'open'), default='hold',
                        help='Após perder a mão: manter posição ou abrir (padrão: hold)')
    result.add_argument('--lost-timeout', type=float, default=1.0)
    result.add_argument('--list-ports', action='store_true')
    return result


def run(args):
    import cv2
    import numpy as np

    calibration = load_calibration(args.config)
    tracker = GestureTracker()
    capture = None
    with ExitStack() as stack:
        if not args.headless:
            if os.name != 'nt' and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
                raise RuntimeError('Sem sessão gráfica. Use --headless.')
            stack.callback(cv2.destroyAllWindows)
        if not args.demo:
            capture = cv2.VideoCapture(args.camera)
            stack.callback(capture.release)
            if not capture.isOpened():
                raise RuntimeError(f'Câmera {args.camera} indisponível. Verifique a conexão ou use --demo.')
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            import mediapipe as mp
            detector = stack.enter_context(mp.solutions.hands.Hands(
                max_num_hands=1, min_detection_confidence=0.6, min_tracking_confidence=0.6))
        controller = stack.enter_context(HandController(
            calibration, port=args.port, simulate=args.simulate or args.demo))
        logging.info('Modo: %s. Saída: Q, Esc ou Ctrl+C.',
                     'DEMONSTRAÇÃO SINTÉTICA' if args.demo else ('CÂMERA / SERVOS SIMULADOS' if args.simulate else 'ARDUINO'))
        last_seen = time.monotonic()
        lost = False
        count = 0
        while not args.frames or count < args.frames:
            started = time.monotonic()
            if args.demo:
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                landmarks = demo_landmarks((count // 45) % 2 == 0)
                for point in landmarks:
                    cv2.circle(frame, (int(320 + point[0] * 65), int(370 - point[1] * 65)), 5, (80, 220, 140), -1)
            else:
                success, frame = capture.read()
                if not success or frame is None:
                    raise RuntimeError('Falha na leitura da câmera. A captura foi encerrada.')
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = detector.process(rgb)
                landmarks = None
                if result.multi_hand_world_landmarks:
                    landmarks = [(p.x, p.y, p.z) for p in result.multi_hand_world_landmarks[0].landmark]
                    if result.multi_hand_landmarks:
                        mp.solutions.drawing_utils.draw_landmarks(
                            frame, result.multi_hand_landmarks[0], mp.solutions.hands.HAND_CONNECTIONS)
            now = time.monotonic()
            if landmarks is not None:
                last_seen = now
                lost = False
                controller.update(tracker.update(landmarks), now=now)
                status = 'Mao detectada'
            else:
                tracker.reset()
                status = 'Sem mao - mantendo posicao'
                if now - last_seen >= args.lost_timeout:
                    if not lost:
                        logging.info('Mão ausente: %s.', args.lost_action)
                        lost = True
                    if args.lost_action == 'open':
                        controller.update({name: True for name in calibration}, now=now)
                        status = 'Sem mao - abrindo'
            if not args.headless:
                title = 'DEMO: gestos sinteticos' if args.demo else ('Camera / servos simulados' if args.simulate else 'Camera / Arduino')
                cv2.putText(frame, title, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (80, 220, 140), 2)
                cv2.putText(frame, status, (15, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
                for row, (name, angle) in enumerate(controller.angles.items()):
                    cv2.putText(frame, f'{name}: {angle} graus', (15, 95 + 25 * row), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                cv2.imshow('Mao robotica - Q para sair', frame)
                if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
                    break
                if cv2.getWindowProperty('Mao robotica - Q para sair', cv2.WND_PROP_VISIBLE) < 1:
                    break
            count += 1
            time.sleep(max(0, 1 / 30 - (time.monotonic() - started)))
        logging.info('Execução encerrada: %d quadros processados.', count)
    return 0


def main(argv=None):
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if args.frames < 0 or not 0 < args.lost_timeout < float('inf'):
        argument_parser.error('--frames deve ser >= 0 e --lost-timeout deve ser positivo e finito.')
    if not args.list_ports and not (args.demo or args.simulate or args.port):
        argument_parser.error('Informe --port para Arduino, --simulate para câmera ou --demo sem hardware.')
    if args.port and (args.demo or args.simulate):
        argument_parser.error('--port não pode ser combinado com --demo ou --simulate.')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        if args.list_ports:
            from serial.tools.list_ports import comports
            ports = list(comports())
            for port in ports:
                print(f'{port.device}: {port.description}')
            if not ports:
                print('Nenhuma porta serial encontrada.')
            return 0
        return run(args)
    except KeyboardInterrupt:
        logging.info('Encerrado pelo usuário.')
        return 0
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        logging.error('%s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
