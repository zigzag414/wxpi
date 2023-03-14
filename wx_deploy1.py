from __future__ import print_function, division
import paho.mqtt.client as mqtt
import qwiic
import time
import sys
import board
from gpiozero import Button
import math
import statistics

import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import busio
import Adafruit_ADS1x15

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import datetime

import adafruit_veml6075

import os
# Changing the CWD
os.chdir('/home/pi/.config/gspread')

#UV SENSOR
i2c = busio.I2C(board.SCL, board.SDA)

#RAINFALL CODE
rain_sensor = Button(6)
BUCKET_SIZE = 0.2794
count = 0

def bucket_tipped():
    global count
    count = count + 1
    #print(count*BUCKET_SIZE)
    
def reset_rainfall():
    global count
    count = 0
    
rain_sensor.when_pressed = bucket_tipped   
# #RAINFALL CODE 

#WIND SPEED CODE

def reset_wind():
    global wind_count
    wind_count=0

store_speeds = []

CM_IN_A_KM = 100000.0
SECS_IN_AN_HOUR=3600

adjustment=1.18 #anemometer factor adjustment

wind_speed_sensor = Button(5)
wind_count = 0 #counts how many half rotations
radius_cm = 9.0 #radius of anemometer
wind_interval = 5   #how often (sec) to report speed
#END WIND SPEED CODE

#START WIND DIRECTION CODE
adc = Adafruit_ADS1x15.ADS1015()
windir = []
#END WIND DIRECTION CODE

#These values are used to give BME280 and CCS811 some time to take samples
initialize=True
n=2

#MQTT Cayenne setup - you will need your own username, password and clientid
#To setup a Cayenne account go to https://mydevices.com/cayenne/signup/
username = "XXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXX"
password = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
clientid = "XXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
mqttc=mqtt.Client(client_id = clientid)
mqttc.username_pw_set(username, password = password)
mqttc.connect("mqtt.mydevices.com", port=1883, keepalive=60)
mqttc.loop_start()

#Qwiic Board define
prox = qwiic.QwiicProximity()
bme = qwiic.QwiicBme280()
ccs = qwiic.QwiicCcs811()

#Begin statements 
prox.begin()
bme.begin()
ccs.begin()

#Used for debugging CCS811
try:
    ccs.begin()    

except Exception as e:
    print(e)

#set MQTT topics (we are not setting topics for everything)
topic_bme_temp = "v1/" + username + "/things/" + clientid + "/data/1"
topic_bme_hum = "v1/" + username + "/things/" + clientid + "/data/2"
topic_bme_pressure = "v1/" + username + "/things/" + clientid + "/data/3"
topic_bme_altitude = "v1/" + username + "/things/" + clientid + "/data/4"

topic_prox_proximity = "v1/" + username + "/things/" + clientid + "/data/5"
topic_prox_ambient = "v1/" + username + "/things/" + clientid + "/data/6"

topic_ccs_temp = "v1/" + username + "/things/" + clientid + "/data/7"
topic_ccs_tvoc = "v1/" + username + "/things/" + clientid + "/data/8"
topic_ccs_co2 = "v1/" + username + "/things/" + clientid + "/data/9"

topic_ws_windspd = "v1/" + username + "/things/" + clientid + "/data/10"
topic_ws_rainfall = "v1/" + username + "/things/" + clientid + "/data/11"
topic_ws_windir = "v1/" + username + "/things/" + clientid + "/data/12"
topic_ws_uvindex = "v1/" + username + "/things/" + clientid + "/data/13"

#Google Sheet Initialization

scopes = [

    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
    
    ]

credentials = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scopes) #access the json key you downloaded earlier 
file = gspread.authorize(credentials) # authenticate the JSON key with gspread
ss = file.open("wxpilog_1")  #open sheet
ws = ss.worksheet('devsht3')  #replace sheet_name with the name that corresponds to yours, e.g, it can be sheet1

def next_available_row(ws):
    str_list = list(filter(None, ws.col_values(1)))
    return str(len(str_list)+1)

#Loop runs until we force an exit or something breaks
while True:
    try:
        if initialize==True:
            print ("Initializing: BME280 and CCS811 are taking samples before printing and publishing data!")
            print (" ")
        else:
            #print ("Finished initializing")
            n=1 #set n back to 1 to read sensor data once in loop
        for n in range (0,n):
            #print ("n = ", n) #used for debugging for loop
            
            #Proximity Sensor variables - these are the available read functions
            #There are additional functions not listed to set thresholds, current, and more
            proximity = prox.get_proximity()
            ambient = prox.get_ambient()
            white = prox.get_white()
            #close = prox.is_close()
            #away = prox.is_away()
            #light = prox.is_light()
            #dark = prox.is_dark()
            #id = prox.get_id()
            
            #BME280 sensor variables
            #reference pressure is available to read or set for altitude calculation
            #referencePressure = bme.get_reference_pressure()
            #bme.set_reference_pressure(referencePressure)
            pressure = bme.get_reference_pressure() #in Pa
            altitudem = bme.get_altitude_meters()
            altitudef = bme.get_altitude_feet()
            humidity = bme.read_humidity()
            tempc = bme.get_temperature_celsius()
            tempf = bme.get_temperature_fahrenheit()
            dewc = bme.get_dewpoint_celsius()
            dewf = bme.get_dewpoint_fahrenheit()
            
            #CCS811 sensor variables 
            #ccsbaseline = get_baseline() #used for telling sensor what 'clean' air is
            #set_baseline(ccsbaseline)
            #error = ccs.check_status_error()
            #data = ccs.data_available()
            #app = ccs.app_valid()
            #errorRegister = ccs.get_error_register()
            #ccs.enable_interrupts()
            #ccs.disable_interrupts()
            #ccs.set_drive_mode(mode) #Mode0=Idle, Mode1=read every 1s, Mode2=read every 10s, Mode3=read every 60s, Mode4=RAW mode
            #ccs.set_environmental_data(humidity,temperature)
            
            ccs.read_algorithm_results() #updates the TVOC and CO2 values
            tvoc = ccs.get_tvoc()
            co2 = ccs.get_co2()
            
            #Note:The following values are used when is a NTC thermistor attached to the CCS811 breakout board
            #the environmental combo does not breakout the pins like the breakout board
            #ccs.set_reference_resistance()
            #ccs.read_ntc() #updates temp value
            #ccstemp = ccs.get_temperature() 
            #ccsres = ccs.get_resistance()
            
            #Weather Station Sensor Variables
            def reset_wind():
                global wind_count
                wind_count=0

            #every half rotation add one to count
            def spin():
                global wind_count
                wind_count = wind_count + 1
    
            #calculate the wind speed
            def calculate_speed(time_sec):
                global wind_count
                circumference_cm = (2*math.pi)*radius_cm
                rotations = wind_count/2.0
        
                dist_km=(circumference_cm*rotations)/CM_IN_A_KM
        
                km_per_sec = dist_km/time_sec
                km_per_hour=km_per_sec*SECS_IN_AN_HOUR
                return km_per_hour * adjustment

            wind_speed_sensor.when_pressed = spin
            
            start_time = time.time()
            while time.time() - start_time <= wind_interval:
                reset_wind()
                time.sleep(wind_interval)
                final_speed = calculate_speed(wind_interval)
                store_speeds.append(final_speed)
                
            #print(store_speeds)
            wind_gust = max(store_speeds)
            #wind_speed = statistics.mean(store_speeds)
            wind_speed = final_speed
            
            #Rainfall
            rainfall = (count*BUCKET_SIZE) 
            
            #Give some time for the BME280 and CCS811 to initialize when starting up
            if initialize==True:
                time.sleep(10)
                initialize=False

            #Wind Direction
            wind =round((adc.read_adc(0)),1)
            if 1250 <= wind <= 1450:
                windir = 0
            elif 1020 <= wind <= 1220:
                windir = 45
            elif 796 <= wind <= 996:
                windir = 90
            elif 221 <= wind <= 421:
                windir = 135 
            elif 0 <= wind <= 102:
                windir = 180
            elif 103 <= wind <= 162:
                windir = 225
            elif 163 <= wind <= 220:
                windir = 270
            elif 498 <= wind <= 698:
                windir = 315 
            else:
                windir = "Unbounded Value"
            
            #UV Sensor 
            veml = adafruit_veml6075.VEML6075(i2c, integration_time=100)

        #printing time and some variables to the screen
        #https://docs.python.org/3/library/time.html
        #print (time.strftime("%a %b %d %Y %H:%M:%S", time.localtime())) #24-hour time 
        print (time.strftime("%a %b %d %Y %I:%M:%S%p", time.localtime())) #12-hour time
        
        print ("BME Temperature %.1f F" %tempf)
        print ("Humidity %.1f" %humidity)
        
        print ("Pressure %.2f Pa" %pressure) 
        print ("Altitude %.2f ft" %altitudef)
        
        #print ("CCS Temperature %.1f F" %ccstemp)
        print ("Distance %.2f " %proximity)
        print ("Ambient Light %.2f" %ambient)
        
        print ("TVOC %.2f" %tvoc)
        print ("CO2 %.2f" %co2)
        
        print("Wind Speed %.2f" %wind_speed)
        print("Wind Direction " + str(windir))
        
        print("Rainfall %.2f" %rainfall)

        print("UV Index %.4f" %veml.uv_index)
        
        print (" ") #blank line for easier readability
        
        #publishing data to Cayenne (we are not publishing everything)
        mqttc.publish (topic_bme_temp, payload = tempf, retain = True)
        mqttc.publish (topic_bme_hum, payload = humidity, retain = True)
        mqttc.publish (topic_bme_pressure, payload = pressure, retain = True)
        mqttc.publish (topic_bme_altitude, payload = altitudef, retain = True)
        
        mqttc.publish (topic_prox_proximity, payload = proximity, retain = True)
        mqttc.publish (topic_prox_ambient, payload = ambient, retain = True)
        
        #mqttc.publish (topic_ccs_temp, payload = ccstemp, retain = True)
        mqttc.publish (topic_ccs_tvoc, payload = tvoc, retain = True)
        mqttc.publish (topic_ccs_co2, payload = co2, retain = True)
        
        mqttc.publish (topic_ws_windspd, payload = wind_speed, retain = True)

        mqttc.publish (topic_ws_rainfall, payload = rainfall, retain = True)
        mqttc.publish (topic_ws_windir, payload = windir, retain = True)
        mqttc.publish (topic_ws_uvindex, payload = veml.uv_index, retain = True)

        #Google Sheets Log
        current_time = datetime.datetime.now()   

        next_row = next_available_row(ws)        
        ws.update_acell("A{}".format(next_row), current_time.year)
        ws.update_acell("B{}".format(next_row), current_time.month)
        ws.update_acell("C{}".format(next_row), current_time.day)
        ws.update_acell("D{}".format(next_row), current_time.hour)
        ws.update_acell("E{}".format(next_row), current_time.minute)
        ws.update_acell("F{}".format(next_row), current_time.second)
        ws.update_acell("G{}".format(next_row), tempf)
        ws.update_acell("H{}".format(next_row), humidity)
        ws.update_acell("I{}".format(next_row), pressure)
        ws.update_acell("J{}".format(next_row), wind_speed)
        ws.update_acell("K{}".format(next_row), windir)
        ws.update_acell("L{}".format(next_row), rainfall)
        ws.update_acell("M{}".format(next_row), ambient)
        ws.update_acell("N{}".format(next_row), veml.uv_index)

        #delay (number of seconds) so we are not constantly displaying data and overwhelming devices
        time.sleep(300)
        
    #if we break things or exit then exit cleanly
    except (EOFError, SystemExit, KeyboardInterrupt):
        mqttc.disconnect()
        sys.exit()

