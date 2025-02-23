import network
import urequests
import ujson
import time
from machine import Pin, PWM, I2C
from machine import Pin, SoftI2C
import framebuf
import socket

# MicroPython SSD1306 OLED driver, I2C and SPI interfaces

from micropython import const


# register definitions
SET_CONTRAST = const(0x81)
SET_ENTIRE_ON = const(0xA4)
SET_NORM_INV = const(0xA6)
SET_DISP = const(0xAE)
SET_MEM_ADDR = const(0x20)
SET_COL_ADDR = const(0x21)
SET_PAGE_ADDR = const(0x22)
SET_DISP_START_LINE = const(0x40)
SET_SEG_REMAP = const(0xA0)
SET_MUX_RATIO = const(0xA8)
SET_COM_OUT_DIR = const(0xC0)
SET_DISP_OFFSET = const(0xD3)
SET_COM_PIN_CFG = const(0xDA)
SET_DISP_CLK_DIV = const(0xD5)
SET_PRECHARGE = const(0xD9)
SET_VCOM_DESEL = const(0xDB)
SET_CHARGE_PUMP = const(0x8D)

# Subclassing FrameBuffer provides support for graphics primitives
# http://docs.micropython.org/en/latest/pyboard/library/framebuf.html
class SSD1306(framebuf.FrameBuffer):
    def __init__(self, width, height, external_vcc):
        self.width = width
        self.height = height
        self.external_vcc = external_vcc
        self.pages = self.height // 8
        self.buffer = bytearray(self.pages * self.width)
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def init_display(self):
        for cmd in (
            SET_DISP | 0x00,  # off
            # address setting
            SET_MEM_ADDR,
            0x00,  # horizontal
            # resolution and layout
            SET_DISP_START_LINE | 0x00,
            SET_SEG_REMAP | 0x01,  # column addr 127 mapped to SEG0
            SET_MUX_RATIO,
            self.height - 1,
            SET_COM_OUT_DIR | 0x08,  # scan from COM[N] to COM0
            SET_DISP_OFFSET,
            0x00,
            SET_COM_PIN_CFG,
            0x02 if self.width > 2 * self.height else 0x12,
            # timing and driving scheme
            SET_DISP_CLK_DIV,
            0x80,
            SET_PRECHARGE,
            0x22 if self.external_vcc else 0xF1,
            SET_VCOM_DESEL,
            0x30,  # 0.83*Vcc
            # display
            SET_CONTRAST,
            0xFF,  # maximum
            SET_ENTIRE_ON,  # output follows RAM contents
            SET_NORM_INV,  # not inverted
            # charge pump
            SET_CHARGE_PUMP,
            0x10 if self.external_vcc else 0x14,
            SET_DISP | 0x01,
        ):  # on
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def poweroff(self):
        self.write_cmd(SET_DISP | 0x00)

    def poweron(self):
        self.write_cmd(SET_DISP | 0x01)

    def contrast(self, contrast):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(SET_NORM_INV | (invert & 1))

    def show(self):
        x0 = 0
        x1 = self.width - 1
        if self.width == 64:
            # displays with width of 64 pixels are shifted by 32
            x0 += 32
            x1 += 32
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(x0)
        self.write_cmd(x1)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_data(self.buffer)


class SSD1306_I2C(SSD1306):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        self.write_list = [b"\x40", None]  # Co=0, D/C#=1
        super().__init__(width, height, external_vcc)

    def write_cmd(self, cmd):
        self.temp[0] = 0x80  # Co=1, D/C#=0
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_data(self, buf):
        self.write_list[1] = buf
        self.i2c.writevto(self.addr, self.write_list)


class SSD1306_SPI(SSD1306):
    def __init__(self, width, height, spi, dc, res, cs, external_vcc=False):
        self.rate = 10 * 1024 * 1024
        dc.init(dc.OUT, value=0)
        res.init(res.OUT, value=0)
        cs.init(cs.OUT, value=1)
        self.spi = spi
        self.dc = dc
        self.res = res
        self.cs = cs
        import time

        self.res(1)
        time.sleep_ms(1)
        self.res(0)
        time.sleep_ms(10)
        self.res(1)
        super().__init__(width, height, external_vcc)

    def write_cmd(self, cmd):
        self.spi.init(baudrate=self.rate, polarity=0, phase=0)
        self.cs(1)
        self.dc(0)
        self.cs(0)
        self.spi.write(bytearray([cmd]))
        self.cs(1)

    def write_data(self, buf):
        self.spi.init(baudrate=self.rate, polarity=0, phase=0)
        self.cs(1)
        self.dc(1)
        self.cs(0)
        self.spi.write(buf)
        self.cs(1)


time.sleep(5)

i2c = SoftI2C(scl=Pin(15), sda=Pin(14))
oled = SSD1306_I2C(128, 64, i2c)
oled.fill(0)

bitdog_big = bytearray(b'\x00\x00\x00\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\x3c\x00\x00\x00\x00\x00\x00\x00\x00\x00\x3e\x00\x00\x00\x00\x00\x00\x00\x00\x00\x37\x00\x00\x00\x00\x00\x00\x00\x00\x01\xf3\x80\x00\x00\x00\x00\x00\x00\x00\x01\xf9\x80\x00\x00\x00\x00\x00\x00\x00\x01\xb8\xc0\x00\x00\x00\x00\x00\x00\x00\x00\x98\x78\x00\x00\x00\x00\x00\x00\x00\x00\xc0\x3f\x80\x00\x00\x00\x00\x00\x00\x01\xc0\x03\xe0\x00\x00\x00\x00\x00\x00\x0f\x80\x00\x78\x03\xe0\x00\x00\x0f\xe0\x1c\x00\x00\x1e\x0f\xf8\x00\x00\x3f\xfc\x70\x00\x00\x07\x7f\xfe\x00\x00\x7f\xfe\xe0\x00\x00\x03\xff\xff\x00\x00\xff\xff\x80\x00\x00\x01\xff\xff\x00\x01\xff\xff\x80\x00\x00\x00\xff\xff\x80\x01\xff\xff\x03\xf0\x0f\x80\xff\xff\xc0\x03\xff\xfe\x07\x38\x1c\xc0\x7f\xff\xc0\x07\xff\xfe\x06\x1c\x30\x60\x7f\xff\xe0\x07\xff\xf6\x0c\x0c\x70\x30\x6f\xff\xe0\x07\xff\xf6\x0c\x7e\x7e\x30\x6f\xff\xf0\x0f\xff\xf6\x08\xfe\x7f\x30\x6f\xff\xf0\x0f\xff\xf6\x08\xfe\x7f\x30\x6f\xff\xf8\x1f\xff\xe6\x08\xfe\x7f\x30\x67\xff\xf8\x1f\xff\xe6\x08\xfe\x7f\x30\x67\xff\xf8\x1f\xff\xe6\x0c\xfe\x7f\x30\x67\xff\xfc\x3f\xff\xe6\x0c\xfc\x3e\x30\x47\xff\xfc\x3f\xff\xe6\x06\x7c\x3c\x60\x43\xff\xfc\x3f\xff\xc6\x03\xf8\x1f\xc0\x43\xff\xfe\x7f\xff\xc2\x01\xf0\x0f\x80\xc3\xff\xfe\x7f\xff\x82\x00\x00\x00\x00\xc1\xff\xfe\x7f\xff\x82\x00\x00\x00\x00\xc1\xff\xfe\x7f\xff\x83\x00\x1e\x78\x00\xc0\xff\xfe\x7f\xff\x03\xf0\x3f\xfc\x07\xe0\xff\xff\xff\xfe\x07\xfe\x3f\xfc\x3f\xf0\x7f\xff\xff\xfe\x0c\x07\xff\xfc\xf0\x18\x7f\xff\xff\xfc\x18\x00\xff\xff\x80\x0c\x3f\xff\xff\xfc\x18\x00\x3f\xfe\x00\x0c\x1f\xff\xff\xf8\x30\x00\x1f\xfc\x00\x06\x0f\xff\xff\xf0\x20\x00\x0f\xf8\x00\x06\x07\xff\xff\xe0\x60\x00\x0f\xf0\x00\x03\x03\xff\x7f\x80\x60\x00\x03\xe0\x00\x03\x00\xfe\x7e\x00\x67\x03\x01\xc0\x81\xe3\x00\x3c\x00\x00\x67\x07\x81\x81\xc1\xe3\x00\x00\x00\x00\x67\x07\x81\x81\xc1\xe3\x00\x00\x00\x00\x60\x03\x01\x81\xc0\x03\x00\x00\x00\x00\x60\x00\x01\x80\x00\x03\x00\x00\x00\x00\x63\x00\x01\x80\x01\x83\x00\x00\x00\x00\x63\x80\x01\x80\x03\xc3\x00\x00\x00\x00\x23\x81\x81\x83\x83\xc6\x00\x00\x00\x00\x33\x83\xc1\x83\x81\x86\x00\x00\x00\x00\x10\x03\xc1\x83\x80\x06\x00\x00\x00\x00\x18\x31\x81\x81\x1c\x0c\x00\x00\x00\x00\x0c\x78\x01\x80\x3c\x18\x00\x00\x00\x00\x06\x78\x01\x80\x1c\x38\x00\x00\x00\x00\x07\x00\x03\xe0\x08\x70\x00\x00\x00\x00\x01\xc0\x1f\x7c\x01\xc0\x00\x00\x00\x00\x00\xff\xfc\x1f\xff\x80\x00\x00\x00\x00\x00\x1f\xe0\x03\xfc\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
fbuf_bdbig = framebuf.FrameBuffer(bitdog_big, 80, 60, framebuf.MONO_HLSB)

# Desenha o BitDog grande no centro do display
oled.blit(fbuf_bdbig, 24, 2)  # Ajustado para centralizar
oled.show()

html = """
 <!DOCTYPE html>
<html>
<head>
    <title>SmartLight</title>
    <style>
        body { text-align: center; font-family: Arial, sans-serif; background-color: black; color: white; }
        .container { margin-top: 50px; }
        button { width: 80px; height: 80px; margin: 10px; border-radius: 20px; font-size: 20px; }
        .btn { display: inline-block; }
    </style>
</head>
<body>
    <h1>SmartLight</h1>
    <div class='container'>
        <button class='btn' onclick="sendRequest('/power')">&#x23FB;</button>
        <button class='btn' onclick="toggleBrightnessPopup()">&#x1F506;</button><br>
        <button class='btn' onclick="togglecolorpopup()">&#x1F3A8;</button>
        <button class='btn' onclick="sendRequest('/effect')">&#x26A1;</button>

    </div>
    <div id="brightnessModal" style="display: none;">
        <p>Ajuste o brilho:</p>
        <input type="range" id="brightnessSlider" min="0" max="100" value="50">
        <button onclick="setBrightness()">OK</button>
        <button onclick="closeBrightnessPopup()">Cancelar</button>
    </div>
    <div id="colorModal" style= "display: none;">
        <p>Ajuste a cor RGB:</p>
        <label>R</label><input type="range" id="redSlider" min="0" max="255" value="128"><br>
        <label>G</label><input type="range" id="greenSlider" min="0" max="255" value="128"><br>
        <label>B</label><input type="range" id="blueSlider" min="0" max="255" value="128"><br>
        <button onclick="setColor()">OK</button>
        <button onclick="closeColorPopup()">Cancelar</button>
    </div>
    <script>
        function sendRequest(path) {
            fetch(path).then(response => console.log("Request sent to" + path));
        }
        
        function showBrightnessPopup() {
            document.getElementById("brightnessModal").style.display = "block";
        }
        
        function closeBrightnessPopup() {
            document.getElementById("brightnessModal").style.display = "none";
        }

        function toggleBrightnessPopup() {
            const brightnessModal = document.getElementById("brightnessModal");
            if(brightnessModal.style.display=="none")
                brightnessModal.style.display = "block"
            else
                brightnessModal.style.display = "none"
        }
        
        function setBrightness() {
            let brightness = document.getElementById("brightnessSlider").value;
            fetch(`/brightness?value=${brightness}`).then(response => console.log("Brightness set to " + brightness));
            closeBrightnessPopup();
        }
        function showColorPopup() {
            document.getElementById("colorModal").style.display = "block";
        }
        
        function closeColorPopup() {
            document.getElementById("colorModal").style.display = "none";
        }
        
        function setColor() {
            let r = document.getElementById("redSlider").value;
            let g = document.getElementById("greenSlider").value;
            let b = document.getElementById("blueSlider").value;
            fetch(`/color?r=${r}&g=${g}&b=${b}`).then(response => console.log(`Color set to R:${r} G:${g} B:${b}`));
            closeColorPopup();
        }
        function togglecolorpopup() {
            const brightnessModal = document.getElementById("brightnessModal");
            if(colorModal.style.display=="none")
            colorModal.style.display = "block"
            else
            colorModal.style.display = "none"
        }
        
    </script>
</body>
</html>
"""

time.sleep(2)

# Configuração do Wi-Fi
SSID = "REDEDOMARCOS"
PASSWORD = "45612300"

# Conexão Wi-Fi
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    while not wlan.isconnected():
        oled.fill(0)
        oled.text("CONECTANDO...", 0, 0)
        oled.show()
        time.sleep(1)
    oled.fill(0)
    oled.text("CONECTADO!", 0, 0)
    oled.show()
    print("Conectado ao Wi-Fi", wlan.ifconfig())

# Configuração do LED RGB
led_r = PWM(Pin(13))
led_g = PWM(Pin(11))
led_b = PWM(Pin(12))
led_r.freq(1000)
led_g.freq(1000)
led_b.freq(1000)

# Configuração do Display
#i2c = I2C(0, scl=Pin(22), sda=Pin(21))
#display = SSD1306_I2C(128, 64, i2c)

# Variáveis de estado
led_state = False
brightness = 512
rgb_values = (512, 512, 512)
power_consumed = 0.0
cost_per_kwh = 0.0

total_led_power = 0.192 
# Controle do LED
def update_led():
    if led_state and brightness > 0:
        led_r.duty_u16(int((rgb_values[0] * brightness / 100)* 65535 / 255))  # Ajusta o vermelho
        led_g.duty_u16(int((rgb_values[1] * brightness / 100)* 65535 / 255))  # Ajusta o verde
        led_b.duty_u16(int((rgb_values[2] * brightness / 100)* 65535 / 255))  # Ajusta o azul
    else:
        led_r.duty_u16(0)
        led_g.duty_u16(0)
        led_b.duty_u16(0)

# Servidor Web
start_time = time.time()
power_consumed = 0.0
def start_server():
    terminou= False
    addr = socket.getaddrinfo("0.0.0.0", 8080)[0][-1]
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    while not terminou:
        try:
            s.bind(addr)
            s.listen(5)
            print("Servidor rodando...")
            terminou=True
        except OSError as e:
            time.sleep(5)
            print(f' >> ERROR: {e}')
        except KeyboardInterrupt:
            s.close()
            print("Código finalizado")
                
    
    while True:
        try:
            cl, addr = s.accept()
            request = cl.recv(1024).decode()
            print("Requisição recebida:", request)
        
            global led_state, brightness, rgb_values, power_consumed
            if "/power" in request:
                led_state = not led_state
                if led_state:
                    start_time = time.time()
                else:
                    power_consumed = 0 
            if "/brightness?value=" in request:
                brightness = int(request.split("value=")[1].split(" ")[0])
            if "/color?r=" in request:
                params = request.split("?")[1].split(" ")[0]
                r, g, b = [int(p.split("=")[1]) for p in params.split("&")]
                rgb_values = (r * brightness // 100, g * brightness // 100, b * brightness // 100)
        
            print(f"LED STATE {led_state}")
            custo=0
            power_consumed_kwh=0
            if led_state:
               cost_per_kwh = 0.8
               elapsed_time = time.time() - start_time
               power_consumed = (brightness / 100)* total_led_power *elapsed_time
               power_consumed_kwh=(power_consumed/3600000)
               custo = power_consumed_kwh*cost_per_kwh
            update_led()
            oled.fill(0)  
            oled.text('Gasto de Energia:', 0, 0)
            oled.text(f'{power_consumed_kwh:.7f} kWh', 0, 20)
            oled.text(f'Custo: {custo:.2f} R$', 0, 40)
            oled.show() 
            cl.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
            cl.send(html)
            cl.close()
        except KeyboardInterrupt:
            s.close()
            print("Código finalizado")
        
connect_wifi()
start_server()