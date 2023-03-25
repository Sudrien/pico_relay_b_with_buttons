import time
import machine
import rp2
import micropython

PIN_NUM = 13
pwm = machine.PWM(machine.Pin(6))
pwm.freq(600)

@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT, autopull=True, pull_thresh=24)
def ws2812():
    T1 = 2
    T2 = 5
    T3 = 3
    wrap_target()
    label("bitloop")
    out(x, 1)               .side(0)    [T3 - 1]
    jmp(not_x, "do_zero")   .side(1)    [T1 - 1]
    jmp("bitloop")          .side(1)    [T2 - 1]
    label("do_zero")
    nop()                   .side(0)    [T2 - 1]
    wrap()
    
class RelayBox(object):
    def __init__(self,pin=PIN_NUM,num=1,brightness=0.8):
        self.pin=pin
        self.num=num
        self.brightness = brightness
        # Create the StateMachine with the ws2812 program, outputting on pin
        self.sm = rp2.StateMachine(0, ws2812, freq=8_000_000, sideset_base=machine.Pin(PIN_NUM))

        # Start the StateMachine, it will wait for data on its FIFO.
        self.sm.active(1)
        
        self.overhead_power = machine.Pin(21, machine.Pin.OUT)
        self.yellow_power = machine.Pin(20, machine.Pin.OUT)
        self.logic_power = machine.Pin(19, machine.Pin.OUT)
        self.blue_power = machine.Pin(18, machine.Pin.OUT)
        self.filter_power = machine.Pin(17, machine.Pin.OUT)
        self.green_power = machine.Pin(16, machine.Pin.OUT)
        
        self.overhead_toggle = 0
        self.logic_toggle = 0
        self.filter_toggle = 0

        self.green_button = machine.Pin(1, machine.Pin.IN, machine.Pin.PULL_UP)
        self.green_button.irq(handler = self.green_debounce, trigger=machine.Pin.IRQ_FALLING )
        
        self.yellow_button = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)
        self.yellow_button.irq(handler = self.yellow_debounce, trigger=machine.Pin.IRQ_FALLING )
        
        self.blue_button = machine.Pin(3, machine.Pin.IN, machine.Pin.PULL_UP)
        self.blue_button.irq(handler = self.blue_debounce, trigger=machine.Pin.IRQ_FALLING )
    
        self.yellow_handler_actual_ref = self.yellow_handler_actual
        self.green_handler_actual_ref = self.green_handler_actual
        self.blue_handler_actual_ref = self.blue_handler_actual
        self.yellow_rebounce_ref = self.yellow_rebounce
        self.green_rebounce_ref = self.green_rebounce
        self.blue_rebounce_ref = self.blue_rebounce
        
        self.yellow_timer = machine.Timer()
        self.green_timer = machine.Timer()
        self.blue_timer = machine.Timer()
        
        self.yellow_block = 0
        self.green_block = 0
        self.blue_block = 0
        
    def yellow_debounce(self, pin_data):
        if not self.yellow_block:
            print('yellow no bounce', pin_data)
            self.yellow_block = 1
            # schedule clogs up too quick, use the timer twice per valid press
            # micropython.schedule(self.yellow_handler_actual_ref, 0) 
            self.yellow_timer.init(mode=machine.Timer.ONE_SHOT, period=1, callback=self.yellow_handler_actual_ref)
    def yellow_handler_actual(self, _):
        print("yellow handler")
        if self.overhead_power.value():
            self.Relay_CHx(relay_box.yellow_power, 0)
            self.Relay_CHx(relay_box.overhead_power, 0)
        else:
            self.Relay_CHx(relay_box.yellow_power, 1)
            self.Relay_CHx(relay_box.overhead_power, 1)
        self.yellow_timer.init(mode=machine.Timer.ONE_SHOT, period=1000, callback=self.yellow_rebounce_ref)
    def yellow_rebounce(self, _):
        self.yellow_block = 0
        print('yellow can bounce again')

    def green_debounce(self, pin_data):
        if not self.green_block:
            print('green no bounce')
            self.green_block = 1
            self.green_timer.init(mode= machine.Timer.ONE_SHOT, period=1, callback=self.green_handler_actual_ref)
    def green_handler_actual(self, _):
        print("green handler")
        if self.logic_power.value():
            self.Relay_CHx(relay_box.green_power, 0)
            self.Relay_CHx(relay_box.logic_power, 0)
        else:
            self.Relay_CHx(relay_box.green_power, 1)
            self.Relay_CHx(relay_box.logic_power, 1)
        self.green_timer.init(mode=machine.Timer.ONE_SHOT, period=1000, callback=self.green_rebounce_ref)
    def green_rebounce(self, _):
        self.green_block = 0
        print('green can bounce again')
        
    def blue_debounce(self, pin_data):
        if not self.blue_block:
            print('blue no bounce')
            self.blue_block = 1
            self.blue_timer.init(mode=machine.Timer.ONE_SHOT, period=1, callback=self.blue_handler_actual_ref)
    def blue_handler_actual(self, _):
        print("blue handler")
        if self.filter_power.value():
            self.Relay_CHx(relay_box.blue_power, 0)
            self.Relay_CHx(relay_box.filter_power, 0)
        else:
            self.Relay_CHx(relay_box.blue_power, 1)
            self.Relay_CHx(relay_box.filter_power, 1)
        self.blue_timer.init(mode=machine.Timer.ONE_SHOT, period=1000, callback=self.blue_rebounce_ref)
    def blue_rebounce(self, _):
        self.blue_block = 0
        print('blue can bounce again')
    
    ##########################################################################
    def pixels_show(self):
        dimmer_ar = array.array("I", [0 for _ in range(self.num)])
        for i,c in enumerate(self.ar):
            r = int(((c >> 8) & 0xFF) * self.brightness)
            g = int(((c >> 16) & 0xFF) * self.brightness)
            b = int((c & 0xFF) * self.brightness)
            dimmer_ar[i] = (g<<16) + (r<<8) + b
        self.sm.put(dimmer_ar, 8)

    def pixels_set(self, i, color):
        self.ar[i] = (color[1]<<16) + (color[0]<<8) + color[2]
     
    def wheel(self, pos):
        # Input a value 0 to 31 to get a color value.
        # The colours are a transition r - g - b - back to r.
        if pos < 0 or pos > 255:
            return (0, 0, 0)
        if pos < 85:
            return (255 - pos * 3, pos * 3, 0)
        if pos < 170:
            pos -= 85
            return (0, 255 - pos * 3,pos * 3)
        pos -= 170
        return (pos * 3, 0, 255 - pos * 3)
     
     
    def rainbow_cycle(self, wait):
        for j in range(256):
            for i in range(self.num):
                rc_index = (i * 256 // self.num) + j
                self.pixels_set(i, self.wheel(rc_index & 255))
            self.pixels_show()
            time.sleep(wait)
    def Relay_CHx(self,n,switch): 
        if switch == 1:
            n.high()
        else:
            n.low()

if __name__=='__main__':
    relay_box = RelayBox()

    while True:
        time.sleep(1)
        
#todo: detect power loss, don't turn things back on without actual button press
#usb interface for octoprint control
