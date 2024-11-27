import time
import threading
from flask import Flask, request, jsonify
import requests_controller
from time import sleep
import sys
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
from rpi_ws281x import PixelStrip, Color
import signal

# Configuración del LED WS2812
LED_COUNT = 3        # Número de LEDs en la tira
LED_PIN = 18         # Pin GPIO donde está conectado el cable de datos del LED >
LED_FREQ_HZ = 800000 # Frecuencia de seÃ±al (800kHz típico para WS2812)
LED_DMA = 10         # DMA para la transmisiÃ³n de datos
LED_BRIGHTNESS = 255 # Brillo mÃ¡ximo (0 a 255)
LED_INVERT = False   # True si estÃ¡s usando un transistor de inversiÃ³n
LED_CHANNEL = 0      # Canal 0 para GPIO 18

# Configuración del buzzer
buzzer_pin = 23
GPIO.setmode(GPIO.BCM)
GPIO.setup(buzzer_pin, GPIO.OUT)

# Inicializa el LED
strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
strip.begin()

# Colores definidos
BLUE = Color(0, 0, 255)   # Azul
GREEN = Color(0, 255, 0)  # Verde
RED = Color(255, 0, 0) # Rojo

# Inicializa el lector RFID
reader = SimpleMFRC522()

# Inicia el PWM para el buzzer
pwm = GPIO.PWM(buzzer_pin,360)  # Configura el buzzer con frecuencia inicial

backend = requests_controller.RequestsController(
    endpoint="https://rayiot.eastus2.cloudapp.azure.com/odoo-firebase-core/odoo-import",
    access_token="12fa06f23b81d89482ebadc754d20009272e2181e7c8f42759dbafcfd89c9c49",
    account_id=1
)

app = Flask(__name__)

# Variable global para almacenar user_id al registrar usuario
user_id = None

# Variable global para controlar el estado del modo de registro
mode = None  # Indica el modo activo: 'register' o 'attendance'

def run_server():
    """Función para ejecutar el servidor Flask."""
    app.run(host="0.0.0.0", port=5000)

# FunciÃ³n para establecer color del LED
def set_led_color(color):
    for i in range(LED_COUNT):
        strip.setPixelColor(i, color)
    strip.show()

def buzzer_success():
    # Activar el buzzer con secuencia de tonos
    pwm.stop()
    pwm.start(50)  # Duty cycle 50%
    pwm.ChangeFrequency(280)
    sleep(0.2)
    pwm.ChangeFrequency(360)
    sleep(0.2)
    pwm.stop()

def buzzer_fail():
    # Activar el buzzer con secuencia de tonos
    pwm.stop()
    pwm.start(50)  # Duty cycle 50%
    pwm.ChangeFrequency(360)
    sleep(0.2)
    pwm.ChangeFrequency(280)
    sleep(0.2)
    pwm.stop()

# Variable global para controlar el ciclo principal
running = True
def signal_handler(sig, frame):
    """Maneja la interrupción del usuario con Ctrl+C."""
    global running
    print("\nDeteniendo el servidor y limpiando recursos...")
    running = False
    GPIO.cleanup()  # Asegúrate de limpiar los pines GPIO
    pwm.stop()      # Detén el PWM si lo estás usando
    set_led_color(Color(0, 0, 0))  # Apaga el LED
    sleep(1)  # Da tiempo para que otros procesos se limpien
    exit(0)

@app.route('/register_mode', methods=['POST'])
def register_mode():
    """Endpoint para registrar un modo con user_id."""
    global user_id, mode
    data = request.json

    if 'user_id' not in data:
        return jsonify({"error": "user_id es requerido"}), 400

    user_id = data['user_id']
    print(f"user_id recibido: {user_id}")

    mode = 'register'

    return jsonify({"success": True, "message": "Id del usuario recibido"}), 200

@app.route('/attendance_mode', methods=['POST'])
def attendance_mode():
    global mode

    mode = 'attendance'

    return {'success': False, 'message': 'Correct'}


def register_attendance_mode():
    try:
        set_led_color(BLUE)
        print("Escanéa un tarjeta NFC")

        # Leer tarjeta RFID
        id, text = reader.read()

        payload = {
            'nfc_id': str(id)
        }

        if id:
            try:
                response = backend.make_request(
                    method="register_assistence",
                    payload=payload,
                    res_model="ray.user.event"
                )

                if response.get('result', {}).get('success', False):
                    set_led_color(GREEN)
                    buzzer_success()
                    print("Asistencia registrada exitosamente.")
                else:
                    set_led_color(RED)
                    buzzer_fail()
                    print("Error al registrar asistencia.")

                sleep(3)
            except Exception as e:
                print(f"Ha ocurrido un error: {e}")
    except KeyboardInterrupt:
        # Limpieza de GPIO y apagado del LED
        print("Program interrupted")


def register_user_mode():
    try:
        set_led_color(BLUE)  # Indica que está listo para leer
        print("Escanéa una tarjeta NFC")

        # Leer tarjeta NFC (espera a que se lea una)
        id, text = reader.read()
        print(f"Tarjeta leída: ID={id}, Texto={text}")  # Depuración

        payload = {
            'nfc_id': str(id)
        }

        # Intentar enviar la petición al backend
        if id:
            try:
                response = backend.make_request(
                    method="set_nfc",
                    payload=payload,
                    res_model="ray.user",
                    res_id=user_id
                )

                # Verificar la estructura de la respuesta
                if response.get('result', {}).get('success', False):
                    set_led_color(GREEN)
                    buzzer_success()
                    print("Asistencia registrada exitosamente.")
                else:
                    set_led_color(RED)
                    buzzer_fail()
                    print("Error al registrar asistencia.")

                time.sleep(3)

            except Exception as e:
                print(f"Ha ocurrido un error al enviar la petición: {e}")

    except KeyboardInterrupt:
        print("Lectura interrumpida por el usuario")

signal.signal(signal.SIGINT, signal_handler)

if __name__ == "__main__":
    # Iniciar el servidor Flask en un hilo separado
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    while True:
        set_led_color(BLUE)
        try:
            if mode == 'register':
                register_user_mode()
            elif mode == 'attendance':
                register_attendance_mode()

        except KeyboardInterrupt:
            print("\nDeteniendo el servidor y limpiando recursos...")
            GPIO.cleanup()
            pwm.stop()
            set_led_color(Color(0, 0, 0))
