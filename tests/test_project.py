import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'mao-robotica-mediapipe-main'))
from gestos import GestureTracker, demo_landmarks
from servo_braco3d import HandController, load_calibration
import main


class GestureTests(unittest.TestCase):
    @staticmethod
    def index_pose(proximal, distal):
        points = demo_landmarks(True)
        first_bend = math.radians(180 - proximal)
        second_bend = first_bend + math.radians(180 - distal)
        points[7] = (-1., 2. + math.cos(first_bend), math.sin(first_bend))
        points[8] = (-1., points[7][1] + math.cos(second_bend),
                     points[7][2] + math.sin(second_bend))
        return points

    def test_index_reopens_with_slightly_bent_tip(self):
        for distal in (135, 145, 150):
            with self.subTest(distal=distal):
                tracker = GestureTracker()
                for _ in range(3):
                    tracker.update(demo_landmarks(False))
                points = self.index_pose(170, distal)
                for _ in range(2):
                    self.assertFalse(tracker.update(points)['indicador'])
                states = tracker.update(points)
                self.assertTrue(states['indicador'])
                self.assertTrue(all(states.values()))

    def test_index_still_closes_at_either_joint(self):
        for proximal, distal in ((120, 175), (175, 90)):
            with self.subTest(proximal=proximal, distal=distal):
                tracker = GestureTracker()
                for _ in range(3):
                    tracker.update(demo_landmarks(True))
                points = self.index_pose(proximal, distal)
                for _ in range(2):
                    self.assertTrue(tracker.update(points)['indicador'])
                states = tracker.update(points)
                self.assertFalse(states['indicador'])
                self.assertTrue(all(state for name, state in states.items() if name != 'indicador'))

    def test_index_ambiguous_tip_holds_previous_state(self):
        for opened in (True, False):
            tracker = GestureTracker()
            for _ in range(3):
                tracker.update(demo_landmarks(opened))
            for _ in range(10):
                self.assertEqual(tracker.update(self.index_pose(170, 125))['indicador'], opened)

    def test_rotation_scale_and_translation(self):
        for opened in (True, False):
            points = demo_landmarks(opened)
            # Rotação 3D, espelhamento, escala e translação não mudam o gesto.
            for scale in (0.01, 5):
                transformed = [(10 - scale*z, 20 + scale*x, 30 + scale*y) for x, y, z in points]
                tracker = GestureTracker()
                for _ in range(3):
                    states = tracker.update(transformed)
                self.assertEqual(states, {name: opened for name in load_calibration()})

    def test_noise_requires_consecutive_frames(self):
        tracker = GestureTracker()
        self.assertEqual(tracker.update(demo_landmarks(True)), {})
        self.assertEqual(tracker.update(demo_landmarks(False)), {})
        self.assertEqual(tracker.update(demo_landmarks(True)), {})
        self.assertEqual(tracker.update(demo_landmarks(True)), {})
        self.assertTrue(all(tracker.update(demo_landmarks(True)).values()))
        self.assertTrue(all(tracker.update(demo_landmarks(False)).values()))

    def test_loss_resets_confirmation(self):
        tracker = GestureTracker()
        tracker.update(demo_landmarks(True))
        tracker.update(demo_landmarks(True))
        tracker.reset()
        self.assertEqual(tracker.update(demo_landmarks(True)), {})

    def test_invalid_landmarks(self):
        for points in ([], [(0, 0, 0)] * 21, [(math.nan, 0, 0)] * 21):
            self.assertEqual(GestureTracker().update(points), {})


class ServoTests(unittest.TestCase):
    def test_only_changes_are_written_and_rate_is_limited(self):
        board = Mock()
        board.digital = [Mock() for _ in range(14)]
        with patch('pyfirmata2.Arduino', return_value=board):
            with HandController(load_calibration(), port='fake') as hand:
                board.servo_config.assert_any_call(9, angle=130)
                hand.update({'indicador': False}, now=0)
                hand.update({'indicador': False}, now=0.1)
                hand.update({'indicador': True}, now=0.11)
                self.assertEqual(board.digital[9].write.call_count, 1)
                self.assertEqual(board.digital[9].write.call_args.args, (0,))
                hand.update({'indicador': True}, now=0.2)
                self.assertEqual(board.digital[9].write.call_args.args, (130,))
                self.assertEqual(board.digital[9].write.call_count, 2)
            board.exit.assert_called_once()

    def test_closes_on_exception(self):
        board = Mock()
        board.digital = [Mock() for _ in range(14)]
        with patch('pyfirmata2.Arduino', return_value=board):
            with self.assertRaises(RuntimeError):
                with HandController(load_calibration(), port='fake'):
                    raise RuntimeError('camera failure')
        board.exit.assert_called_once()

    def test_missing_firmata_closes_connection(self):
        board = Mock()
        board.get_firmata_version.return_value = None
        with patch('pyfirmata2.Arduino', return_value=board):
            with self.assertRaisesRegex(RuntimeError, 'Firmata'):
                with HandController(load_calibration(), port='fake'):
                    self.fail('Não deve conectar sem Firmata')
        board.exit.assert_called_once()

    def test_bad_calibration_is_rejected(self):
        for change in ({'pin': 9}, {'closed': 181}, {'open': True}):
            data = load_calibration()
            data['polegar'].update(change)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'calibration.json'
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_calibration(path)

    def test_import_has_no_connection_side_effect(self):
        with patch('pyfirmata2.Arduino') as arduino:
            spec = importlib.util.spec_from_file_location('isolated_servo', ROOT / 'mao-robotica-mediapipe-main/servo_braco3d.py')
            spec.loader.exec_module(importlib.util.module_from_spec(spec))
            arduino.assert_not_called()


class LifecycleTests(unittest.TestCase):
    def test_camera_failure_releases_resources(self):
        camera = Mock()
        camera.read.return_value = (False, None)
        detector = Mock()
        detector.__enter__ = Mock(return_value=detector)
        detector.__exit__ = Mock(return_value=False)
        with patch('cv2.VideoCapture', return_value=camera), patch('mediapipe.solutions.hands.Hands', return_value=detector):
            self.assertEqual(main.main(['--simulate', '--headless', '--frames', '1']), 1)
        camera.release.assert_called_once()
        detector.__exit__.assert_called_once()

    def test_unavailable_camera_released_before_board_connection(self):
        camera = Mock()
        camera.isOpened.return_value = False
        with patch('cv2.VideoCapture', return_value=camera), patch('main.HandController') as controller:
            self.assertEqual(main.main(['--port', 'fake', '--headless']), 1)
            controller.assert_not_called()
        camera.release.assert_called_once()

    def test_missing_hand_policy(self):
        import numpy as np
        for action in ('hold', 'open'):
            camera = Mock()
            camera.read.return_value = (True, np.zeros((48, 64, 3), dtype=np.uint8))
            detector = Mock()
            detector.__enter__ = Mock(return_value=detector)
            detector.__exit__ = Mock(return_value=False)
            detector.process.return_value = SimpleNamespace(multi_hand_world_landmarks=None)
            controller = Mock()
            controller.__enter__ = Mock(return_value=controller)
            controller.__exit__ = Mock(return_value=False)
            with patch('cv2.VideoCapture', return_value=camera), patch('mediapipe.solutions.hands.Hands', return_value=detector), patch('main.HandController', return_value=controller), patch('main.time.monotonic', side_effect=[0, 2, 2, 2]):
                self.assertEqual(main.main(['--simulate', '--headless', '--frames', '1', '--lost-action', action]), 0)
            if action == 'hold':
                controller.update.assert_not_called()
            else:
                self.assertEqual(controller.update.call_args.args[0], {name: True for name in load_calibration()})


if __name__ == '__main__':
    unittest.main()
