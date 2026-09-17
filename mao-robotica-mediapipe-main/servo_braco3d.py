"""Conexão explícita e calibração compartilhada para cinco servos."""
import json
import logging
import math
from pathlib import Path
import time

FINGERS = ('polegar', 'indicador', 'medio', 'anelar', 'minimo')


def load_calibration(path=None):
    path = Path(path) if path else Path(__file__).with_name('calibracao.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or set(data) != set(FINGERS):
        raise ValueError('Calibração deve conter exatamente os cinco dedos.')
    pins = []
    for name in FINGERS:
        item = data[name]
        if not isinstance(item, dict) or set(item) != {'pin', 'open', 'closed'}:
            raise ValueError(f'Calibração inválida: {name}. Use pin, open e closed.')
        if type(item['pin']) is not int or not 2 <= item['pin'] <= 13:
            raise ValueError(f'Pino inválido para Arduino Uno: {name}.')
        for key in ('open', 'closed'):
            if type(item[key]) is not int or not 0 <= item[key] <= 180:
                raise ValueError(f'Ângulo inválido: {name}.{key}. Use inteiro de 0 a 180.')
        pins.append(item['pin'])
    if len(set(pins)) != len(pins):
        raise ValueError('Cada dedo precisa de um pino diferente.')
    return {name: data[name] for name in FINGERS}


class HandController:
    def __init__(self, calibration, port=None, simulate=False, rate=20):
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError('Taxa de atualização deve ser positiva e finita.')
        if not simulate and not port:
            raise ValueError('Informe a porta serial do Arduino.')
        self.calibration = calibration
        self.port = port
        self.simulate = simulate
        self.interval = 1 / rate
        self.board = None
        self.angles = {}
        self.last_update = float('-inf')
        self.connected = False

    def __enter__(self):
        if not self.simulate:
            from pyfirmata2 import Arduino
            self.board = Arduino(self.port, timeout=1)
            try:
                if self.board.get_firmata_version() is None:
                    raise RuntimeError('Arduino não respondeu ao Firmata. Grave StandardFirmata na placa.')
                for name, item in self.calibration.items():
                    self.board.servo_config(item['pin'], angle=item['open'])
                    self.angles[name] = item['open']
            except Exception:
                self.close()
                raise
            logging.info('Arduino conectado em %s; Firmata %s.', self.port, self.board.get_firmata_version())
        self.connected = True
        return self

    def update(self, states, now=None):
        if not self.connected:
            raise RuntimeError('Controlador não está conectado.')
        if any(name not in self.calibration or type(state) is not bool for name, state in states.items()):
            raise ValueError('Estados devem associar nomes dos dedos a booleanos.')
        now = time.monotonic() if now is None else now
        if now - self.last_update < self.interval:
            return
        for name, opened in states.items():
            item = self.calibration[name]
            angle = item['open' if opened else 'closed']
            if self.angles.get(name) != angle:
                if self.board is not None:
                    self.board.digital[item['pin']].write(angle)
                self.angles[name] = angle
                logging.info('%s%s: %d° (pino %d)', '[simulado] ' if self.simulate else '', name, angle, item['pin'])
        self.last_update = now

    def close(self):
        self.connected = False
        if self.board is not None:
            board, self.board = self.board, None
            board.exit()

    def __exit__(self, *exc):
        self.close()
