"""Geometria em coordenadas 3D e confirmação temporal de gestos."""
import math

JOINTS = {
    'polegar': (1, 2, 3, 4), 'indicador': (5, 6, 7, 8),
    'medio': (9, 10, 11, 12), 'anelar': (13, 14, 15, 16),
    'minimo': (17, 18, 19, 20),
}


def angle(a, b, c):
    u = [x - y for x, y in zip(a, b)]
    v = [x - y for x, y in zip(c, b)]
    denominator = math.hypot(*u) * math.hypot(*v)
    if denominator < 1e-12:
        return None
    return math.degrees(math.acos(max(-1, min(1, sum(x*y for x, y in zip(u, v)) / denominator))))


class GestureTracker:
    def __init__(self, stable_frames=3):
        if stable_frames < 1:
            raise ValueError('stable_frames deve ser positivo.')
        self.stable_frames = stable_frames
        self.reset()

    def reset(self):
        self.states = {}
        self.pending = {}

    def update(self, points):
        if len(points) != 21 or any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points):
            self.reset()
            return {}
        palm = math.dist(points[5], points[17])
        if palm < 1e-9:
            self.reset()
            return {}
        for name, (a, b, c, d) in JOINTS.items():
            angles = (angle(points[a], points[b], points[c]), angle(points[b], points[c], points[d]))
            if None in angles:
                self.pending.pop(name, None)
                continue
            extension = min(angles)
            opened = extension >= 155
            closed = extension <= 135
            if name == 'indicador':
                # Uma pequena dobra na ponta não deve impedir a reabertura.
                # A junta central mantém os limites originais; a distal tem
                # tolerância maior e sua própria faixa de histerese.
                proximal, distal = angles
                opened = proximal >= 155 and distal >= 135
                closed = proximal <= 135 or distal <= 110
            if name == 'polegar':
                separation = math.dist(points[4], points[5]) / palm
                opened = opened and separation >= 0.6
                closed = closed or separation <= 0.45
            candidate = True if opened else (False if closed else None)
            if candidate is None or candidate == self.states.get(name):
                self.pending.pop(name, None)
                continue
            previous, count = self.pending.get(name, (None, 0))
            count = count + 1 if previous == candidate else 1
            self.pending[name] = (candidate, count)
            if count >= self.stable_frames:
                self.states[name] = candidate
                self.pending.pop(name, None)
        return dict(self.states)


def demo_landmarks(opened):
    """Mão geométrica artificial; não representa inferência da câmera."""
    points = [(0., 0., 0.)] * 21
    for indices, x in zip(list(JOINTS.values())[1:], (-1., 0., 1., 2.)):
        finger = [(x, 1., 0.), (x, 2., 0.), (x, 3., 0.), (x, 4., 0.)] if opened else [
            (x, 1., 0.), (x, 2., 0.), (x, 2., 1.), (x, 1., 1.)]
        for index, point in zip(indices, finger):
            points[index] = point
    thumb = [(-1., 0., 0.), (-2., 1., 0.), (-3., 2., 0.), (-4., 3., 0.)] if opened else [
        (-1., 0., 0.), (-2., 1., 0.), (-1., 1., 0.), (-1., 1., 1.)]
    for index, point in zip(JOINTS['polegar'], thumb):
        points[index] = point
    return points
