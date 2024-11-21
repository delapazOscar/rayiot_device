import time
import threading
from flask import Flask, request, jsonify
import requests_controller
from time import sleep
import sys
import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522
from rpi_ws281x import PixelStrip, Color

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

# FunciÃ³n para establecer color del LED
def set_led_color(color):
    for i in range(LED_COUNT):
        strip.setPixelColor(i, color)
    strip.show()

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
stop_event = threading.Event()  # Evento para detener hilos activos
current_thread = None
def start_mode(new_mode, target_function):
    """
    Cambia el modo activo y lanza un nuevo hilo para ejecutar la función especificada.
    """
    global mode, stop_event, current_thread
    # Detener el hilo actual si está en ejecución
    if mode == new_mode:
        print(f"Modo {new_mode} ya está activo.")
        return

    if current_thread and current_thread.is_alive():
        print(f"Deteniendo modo actual: {mode}")
        stop_event.set()  # Solicita detener el hilo
        current_thread.join()  # Espera a que termine
        print("Hilo anterior detenido.")
    # Cambiar el modo y reiniciar el evento
    mode = new_mode
    stop_event.clear()  # Reinicia el evento para el nuevo hilo
    current_thread = threading.Thread(target=target_function)
    current_thread.start()
    print(f"Modo {new_mode} iniciado.")


def run_server():
    """Función para ejecutar el servidor Flask."""
    app.run(host="0.0.0.0", port=5000)

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

@app.route('/register_mode', methods=['POST'])
def register_mode():
    """Endpoint para registrar un modo con user_id."""
    global user_id
    data = request.json

    if 'user_id' not in data:
        return jsonify({"error": "user_id es requerido"}), 400

    user_id = data['user_id']
    print(f"user_id recibido: {user_id}")
    reader.close()

    # Si ya hay un hilo ejecutándose, cancela y reinicia
    register_thread = threading.Thread(target=register_user_mode)
    register_thread.start()

    return jsonify({"success": True, "message": "Id del usuario recibido"}), 200

@app.route('/attendance_mode', methods=['POST'])
def attendance_mode():
    reader.close()
    start_mode('attendance', loop_attendance_mode)

    return {'success': False, 'message': 'Correct'}

def loop_attendance_mode():
    while not stop_event.is_set():
        register_attendance_mode()

def register_attendance_mode():
    try:
        set_led_color(BLUE)
        print("Escanéa un tarjeta NFC")

        # Leer tarjeta RFID
        id, text = reader.read()

        payload = {
            'nfc_id': str(id)
        }
        try:
            response = backend.make_request(
                method="register_assistence",
                payload=payload,
                res_model="ray.user.event"
            )

            if response and 'result' in response and 'success' in response['result']:
                if response['result']['success']:
                    set_led_color(GREEN)
                    buzzer_success()
                    print("Petición exitosa: Usuario registrado")
                else:
                    set_led_color(RED)
                    buzzer_fail()
                    print(f"Petición fallida: {response['result'].get('message', 'Error desconocido')}")
            else:
                set_led_color(RED)
                buzzer_fail()
                print("Respuesta inesperada del backend")

            sleep(3)
            # Limpiar buzzer
            pwm.stop()
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
        try:
            response = backend.make_request(
                method="set_nfc",
                payload=payload,
                res_model="ray.user",
                res_id=user_id
            )

            # Verificar la estructura de la respuesta
            if response and 'result' in response and 'success' in response['result']:
                if response['result']['success']:
                    set_led_color(GREEN)
                    buzzer_success()
                    print("Petición exitosa: Usuario registrado")
                else:
                    set_led_color(RED)
                    buzzer_fail()
                    print(f"Petición fallida: {response['result'].get('message', 'Error desconocido')}")
            else:
                set_led_color(RED)
                buzzer_fail()
                print("Respuesta inesperada del backend")

            time.sleep(3)

        except Exception as e:
            print(f"Ha ocurrido un error al enviar la petición: {e}")
    except KeyboardInterrupt:
        print("Lectura interrumpida por el usuario")



if __name__ == "__main__":
    # Iniciar el servidor Flask en un hilo separado
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()

    set_led_color(BLUE)

    try:
        print("Servidor Flask escuchando en http://0.0.0.0:5000/register_mode")
        print("Esperando solicitudes para iniciar modos...")
        while True:
            time.sleep(1)  # Mantener el hilo principal activo sin consumir CPU innecesariamente
    except KeyboardInterrupt:
        print("\nDeteniendo el servidor y limpiando recursos...")
        GPIO.cleanup()
        pwm.stop()
        set_led_color(Color(0,0,0))