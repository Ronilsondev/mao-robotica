# Mão robótica por visão computacional

A câmera fornece imagens ao MediaPipe, que estima os 21 pontos da mão.
O programa usa os ângulos das articulações em 3D e a separação relativa do
polegar para classificar cada dedo como aberto ou fechado. Três quadros
consecutivos confirmam a mudança; uma faixa intermediária mantém o estado.
No indicador, a articulação central abre a partir de 155° e fecha até 135°.
A ponta tem mais tolerância (abre a partir de 135° e fecha até 110°), para
uma pequena dobra não prender a classificação em fechado. Para abrir, ambas
precisam atingir seus limites; para fechar, basta uma atingir o limite de fechamento.
O Arduino recebe apenas mudanças de posição, em até 20 atualizações por segundo.

## Instalação

Ambiente validado: Python 3.12. Na raiz do projeto:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

`requirements-lock.txt` registra todas as versões instaladas nesta validação
com Python 3.12. Para reproduzir esse ambiente, use
`.venv/bin/python -m pip install -r requirements-lock.txt`.

No Windows, crie o ambiente com `py -3.12 -m venv .venv` e use
`.venv\Scripts\python.exe` no lugar de `.venv/bin/python`.

As versões são fixadas para manter a API `mediapipe.solutions.hands` usada
neste projeto. Usa-se somente `opencv-contrib-python`, evitando duas
distribuições diferentes instalando o mesmo módulo `cv2`.
O controlador utiliza [pyFirmata2](https://github.com/berndporr/pyFirmata2).

## Executar com câmera e Arduino

A placa deve estar com o firmware `StandardFirmata` gravado. O sketch está em
`StandardFirmata/StandardFirmata.ino`. A configuração de pinos é para Arduino
Uno ou placa com o mesmo mapeamento digital. A detecção da porta USB, sozinha,
não confirma o modelo da placa.

```bash
.venv/bin/python mao-robotica-mediapipe-main/main.py --list-ports
.venv/bin/python mao-robotica-mediapipe-main/main.py --camera 2 --port /dev/ttyUSB0
```

Neste computador, a Logitech C920 foi identificada como câmera **2**, a câmera
integrada como **0** e o adaptador serial CH340 como **/dev/ttyUSB0**.
Esses nomes podem mudar ao reconectar dispositivos. No Windows, informe a
porta correspondente, por exemplo `--port COM3`.

A inicialização envia a posição `open` calibrada a cada servo. Apresente uma
mão à câmera; a janela exibe os pontos e os ângulos enviados. Pressione **Q**,
**Esc**, feche a janela ou use **Ctrl+C** para encerrar. O encerramento libera a
câmera, fecha o detector, desativa os sinais dos servos e fecha a porta serial.

Se a mão desaparecer, o padrão é manter a última posição, sem novos comandos.
Para abrir após um segundo sem detecção, use `--lost-action open`.
O tempo pode ser alterado com `--lost-timeout 2`. Uma falha de captura encerra
a aplicação e libera os recursos. Isso não implementa um watchdog no firmware:
encerramento forçado do processo ou perda da conexão não garantem a mesma limpeza.

## Calibração e teste dos dedos

Edite `mao-robotica-mediapipe-main/calibracao.json`. Tanto o controle por câmera
quanto o teste usam esse arquivo. `--config caminho.json` permite outro perfil.

| Dedo | Pino | Aberto | Fechado |
|---|---:|---:|---:|
| Polegar | 10 | 0° | 150° |
| Indicador | 9 | 130° | 0° |
| Médio | 8 | 130° | 0° |
| Anelar | 7 | 0° | 130° |
| Mínimo | 6 | 130° | 0° |

Os limites angulares foram unificados com a sequência de teste original.
O sentido dos dedos indicador, médio e mínimo foi invertido conforme observado na montagem.
Esses valores não representam uma calibração mecânica medida desta montagem.
Ajuste-os conforme o curso real de cada dedo, sem forçar os limites mecânicos.

```bash
.venv/bin/python mao-robotica-mediapipe-main/testar-dedos.py --port /dev/ttyUSB0
```

Esse comando abre todos os dedos, fecha e abre um de cada vez e encerra.
Feche o rastreamento antes de executar o teste, pois ambos usam a mesma porta.

## Simulação e verificações

```bash
# Câmera real, comandos de servo apenas no terminal
.venv/bin/python mao-robotica-mediapipe-main/main.py --camera 2 --simulate

# Demonstração com pontos artificiais, sem câmera ou Arduino
.venv/bin/python mao-robotica-mediapipe-main/main.py --demo

# Execução limitada sem janela
.venv/bin/python mao-robotica-mediapipe-main/main.py --demo --headless --frames 100

# Testes automatizados sem acionar hardware
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip check
```

A demonstração artificial verifica o fluxo de classificação e comandos,
mas não testa o reconhecimento de uma mão real. Os testes cobrem invariância
geométrica, estabilização, perda da mão, calibração, limite de envio e limpeza
após falhas. A classificação continua sendo uma heurística: oclusões e erros
de estimativa do MediaPipe podem exigir ajustes dos limiares em `gestos.py`.

Em ambientes restritos de desenvolvimento, dispositivos USB e janelas podem
ficar inacessíveis; execute no terminal da sessão gráfica do computador.
