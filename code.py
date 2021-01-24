from secrets import secrets
from adafruit_io.adafruit_io import IO_HTTP
import rtc
from adafruit_magtag.network import Network
import board
import displayio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import label
import adafruit_imageload
import time
from digitalio import DigitalInOut, Direction
from analogio import AnalogIn

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

DIRECTIONS = [ "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW" ]

# Convert degrees to string of the wind diretion
def windDirectionToString(degrees):
    index = (float(degrees) + 11.25) / 22.5
    return DIRECTIONS[int(index%16)]

# Get "limit" values from adafruit IO and average them
def GetAndAverage(feed, limit):
    json_data = io.receive_data_2(feed, limit)
    avg = 0.0
    for value in json_data:
        avg += float(value['value'])
    avg /= len(json_data)
    return avg

# Get "Limit" last values from adafruit IO and add them together
def GetAndSum(feed, limit):
    json_data = io.receive_data_2(feed, limit)
    total = 0.0
    for value in json_data:
        total += float(value['value'])
    return total

# Create a displayio group to show the future weather
def CreateFutureGroup(hour, temp, icon, x = 0, y = 0):
    group = displayio.Group(max_size=4, x=x, y=y)
    next_weather_icon = displayio.TileGrid(
        icons_small_bmp,
        pixel_shader=icons_small_pal,
        x=0,
        y=0,
        width=1,
        height=1,
        tile_width=20,
        tile_height=20,
    )
    next_weather_icon[0] = icon
    group.append(next_weather_icon)

    nextHourTempLabel = label.Label(font_small, text="-99.9", color=0x000000)
    nextHourTempLabel.text = "{:2.1f}".format(temp)
    nextHourTempLabel.anchor_point = (0.5, 0.0)
    nextHourTempLabel.anchored_position = (10, 20)
    group.append(nextHourTempLabel)

    nextHourLabel = label.Label(font_small, text="+8", color=0x000000)
    nextHourLabel.text = "+{}".format(hour)
    nextHourLabel.anchor_point = (0.5, 0.0)
    nextHourLabel.anchored_position = (10, -7)
    group.append(nextHourLabel)

    return group

# Wrap everything in a try block so we can restart if anything fails
try:

    # turn light sensor on
    power = DigitalInOut(board.NEOPIXEL_POWER)
    power.direction = Direction.OUTPUT
    power.value = False

    light_sensor = AnalogIn(board.LIGHT)

    #give it a moment to read (just a guess)
    time.sleep(0.05)

    light_value = light_sensor.value
    power.value = True # turn the sensor offset

    print("Light is:", light_value)

    # No need to update the screen if it is dark and you can't read it
    if light_value > 600:

        display = board.DISPLAY
        display_group = displayio.Group(max_size=25)

        # Set background to white
        color_bitmap = displayio.Bitmap(display.width, display.height, 1)
        color_palette = displayio.Palette(1)
        color_palette[0] = 0xFFFFFF
        bg_sprite = displayio.TileGrid(
            color_bitmap,
            pixel_shader=color_palette,
            x=0,
            y=0,
        )
        display_group.append(bg_sprite)
        display.show(display_group)

        bg_file = open("bg.bmp", "rb")
        background = displayio.OnDiskBitmap(bg_file)
        bg_sprite = displayio.TileGrid(
            background,
            pixel_shader=displayio.ColorConverter(),
            x=0,
            y=0,
        )
        display_group.append(bg_sprite)

        # Load the icon images. Map, maps openweatherapi icon numbers to the position we have
        ICON_MAP = ("01", "02", "03", "04", "09", "10", "11", "13", "50")
        icons_large_bmp, icons_large_pal = adafruit_imageload.load("weather_icons_50px.bmp")
        icons_small_bmp, icons_small_pal = adafruit_imageload.load("weather_icons_20px.bmp")
        icons_bmp, icons_pal = adafruit_imageload.load("icons.bmp")

        # Setup the magtag network and get an adafruit IO client to use
        network = Network()
        io = network._get_io_client()

        # Get info from open weather map API
        print("Connecting to openweatherapi")
        API = "https://api.openweathermap.org/data/2.5/onecall?lon=-97.147&lat=49.8844&APPID=" + secrets['openweather_key'] + "&units=metric&exclude=minutely,alerts"
        response = network.fetch(API)
        jsondata = response.json()
        response.close()

        tzone_offset = jsondata['timezone_offset'] # time zone offset for API times
        current_weather = jsondata['current'] # weather currently happening
        daily_weather = jsondata['daily'] # next 7 days weather including today
        hourly_weather = jsondata['hourly'] # next 48 hours

        sunrise = time.localtime(current_weather["sunrise"] + tzone_offset)
        sunset = time.localtime(current_weather["sunset"] + tzone_offset)

        dailyMin = daily_weather[0]['temp']['min']
        dailyMax = daily_weather[0]['temp']['day'] # use daytime high, daily high may be at a weird time

        nextDayMin = daily_weather[1]['temp']['min']
        nextDayMax = daily_weather[1]['temp']['max']
        nextDayWeather = daily_weather[1]['weather'][0]

        nextHourTemp = hourly_weather[1]['temp']
        nextHourWeather = ICON_MAP.index(hourly_weather[1]["weather"][0]["icon"][:2])

        # Get weather values from Adafruit IO
        print("Reading from Adafruit IO")
        temperature = GetAndAverage("temperature", 5)
        pressure = GetAndAverage("pressure", 5)
        humidity = GetAndAverage("humidity", 5)
        windspeed = GetAndAverage("wind-speed", 1)
        windgust = GetAndAverage("wind-gust", 1)
        winddirection = GetAndAverage("wind-direction", 1)
        winddir = windDirectionToString(winddirection)
        rain = GetAndSum("rain", 60)
        batteryvoltage = GetAndAverage("battery-voltage", 1)

        # Get pressure trend from Adafruit IO
        # If for some reason the data doesn't exist just set it to zero
        try:
            jsondata = io.receive_data_3("pressure", 6, 60)["data"]
            pressureDiff = float(jsondata[len(jsondata)-1][1]) - float(jsondata[0][1])
        except:
            pressureDiff = 0.0

        pressureDiffText = ""
        # No room to show rapidly right now :(
        #if abs(pressureDiff) > 0.35:
            #pressureDiffText += "Rapidly "

        if abs(pressureDiff) < 0.15:
            pressureDiffText += "Steady"
        else:
            if pressureDiff > 0.15:
                pressureDiffText += "Rising"
            elif pressureDiff < 0.15:
                pressureDiffText += "Falling"

        ## UI Follows
        print("Showing UI")

        # Load the fonts
        font40b = bitmap_font.load_font("/SourceSerifPro-Black-40.pcf")
        font_large = bitmap_font.load_font("/SourceSerifPro-Regular-32.pcf")
        font_medium = bitmap_font.load_font("/SourceSerifPro-Regular-16.pcf")
        font_small = bitmap_font.load_font("/SourceSerifPro-Regular-12.pcf")

        todayLabel = label.Label(font_medium, text="Wednesday", color=0x000000) #95 35
        todayLabel.text = DAYS[time.localtime(current_weather['dt']+tzone_offset).tm_wday]
        todayLabel.anchor_point = (0.5, 0.0)
        todayLabel.anchored_position = (148, 4)
        display_group.append(todayLabel)

        tempLabel = label.Label(font40b, text="-99.9°C", color=0x000000) #95 35
        tempLabel.text = "{:1.1f}°C".format(temperature)
        tempLabel.anchor_point = (0.5, 0.0)
        tempLabel.anchored_position = (148, 24)
        display_group.append(tempLabel)

        windLabel = label.Label(font_medium, text="88.8/88.8km/h", color=0x000000)
        windLabel.text = "{:2.1f}/{:2.1f}km/h".format(windspeed, windgust)
        windLabel.anchor_point = (0.5, 0.0)
        windLabel.anchored_position = (148, 55)
        display_group.append(windLabel)

        windDirLabel = label.Label(font_medium, text="NNE", color=0x000000)
        windDirLabel.text = "{}".format(winddir)
        windDirLabel.anchor_point = (0.5, 0.0)
        windDirLabel.anchored_position = (148, 70)
        display_group.append(windDirLabel)

        pressureLabel = label.Label(font_medium, text="88.8/88.8km/h NNE", color=0x000000, x=5, y=65)
        pressureLabel.text = "{:3.1f}kPa".format(pressure)
        display_group.append(pressureLabel)

        pressureTextLabel = label.Label(font_medium, text="88.8/88.8km/h NNE", color=0x000000, x=5, y=80)
        pressureTextLabel.text = pressureDiffText
        display_group.append(pressureTextLabel)

        humidityLabel = label.Label(font_medium, text="100.0%RH", color=0x000000, x=5, y=100)
        humidityLabel.text = "{:3.1f}%".format(humidity)
        display_group.append(humidityLabel)

        rainLabel = label.Label(font_medium, text="100.0%RH", color=0x000000, x=5, y=115)
        rainLabel.text = "{:1.1f}mm".format(rain)
        display_group.append(rainLabel)

        sunrise_icon = displayio.TileGrid(
            icons_bmp,
            pixel_shader=icons_pal,
            x=220,
            y=5,
            width=1,
            height=1,
            tile_width=20,
            tile_height=20,
        )
        sunrise_icon[0] = 2
        display_group.append(sunrise_icon)

        sunriseLabel = label.Label(font_medium, text="11:11 AM", color=0x000000)
        sunriseLabel.text = "{:2d}:{:02d}am".format(sunrise.tm_hour, sunrise.tm_min)
        sunriseLabel.anchor_point = (1.0, 0.0)
        sunriseLabel.anchored_position = (294, 7)
        display_group.append(sunriseLabel)

        sunset_icon = displayio.TileGrid(
            icons_bmp,
            pixel_shader=icons_pal,
            x=220,
            y=25,
            width=1,
            height=1,
            tile_width=20,
            tile_height=20,
        )
        sunset_icon[0] = 3
        display_group.append(sunset_icon)

        sunsetLabel = label.Label(font_medium, text="11:11 AM", color=0x000000)
        sunsetLabel.text = "{:2d}:{:02d}pm".format(sunset.tm_hour - 12, sunset.tm_min)
        sunsetLabel.anchor_point = (1.0, 0.0)
        sunsetLabel.anchored_position = (294, 27)
        display_group.append(sunsetLabel)

        high_icon = displayio.TileGrid(
            icons_bmp,
            pixel_shader=icons_pal,
            x=220,
            y=45,
            width=1,
            height=1,
            tile_width=20,
            tile_height=20,
        )
        high_icon[0] = 1
        display_group.append(high_icon)

        highLabel = label.Label(font_medium, text="H -99.9°C", color=0x000000) #230/10
        highLabel.text = "{:1.1f}°C".format(dailyMax)
        highLabel.anchor_point = (1.0, 0.0)
        highLabel.anchored_position = (288, 50)
        display_group.append(highLabel)

        low_icon = displayio.TileGrid(
            icons_bmp,
            pixel_shader=icons_pal,
            x=220,
            y=65,
            width=1,
            height=1,
            tile_width=20,
            tile_height=20,
        )
        low_icon[0] = 0
        display_group.append(low_icon)

        lowLabel = label.Label(font_medium, text="L -99.9°C", color=0x000000) #230/30
        lowLabel.text = "{:1.1f}°C".format(dailyMin)
        lowLabel.anchor_point = (1.0, 0.0)
        lowLabel.anchored_position = (288, 68)
        display_group.append(lowLabel)


        current_weather_icon = displayio.TileGrid(
            icons_large_bmp,
            pixel_shader=icons_large_pal,
            x=10,
            y=5,
            width=1,
            height=1,
            tile_width=50,
            tile_height=50,
        )
        current_weather_icon[0] = ICON_MAP.index(current_weather["weather"][0]["icon"][:2])
        display_group.append(current_weather_icon)

        # Next weather for the next 1/2/4/8 hours
        nextHourGroup = CreateFutureGroup(1, hourly_weather[1]['temp'] ,ICON_MAP.index(hourly_weather[1]["weather"][0]["icon"][:2]), x=90, y=95)
        display_group.append(nextHourGroup)
        nextHourGroup = CreateFutureGroup(2, hourly_weather[2]['temp'] ,ICON_MAP.index(hourly_weather[2]["weather"][0]["icon"][:2]), x=120, y=95)
        display_group.append(nextHourGroup)
        nextHourGroup = CreateFutureGroup(4, hourly_weather[4]['temp'] ,ICON_MAP.index(hourly_weather[4]["weather"][0]["icon"][:2]), x=150, y=95)
        display_group.append(nextHourGroup)
        nextHourGroup = CreateFutureGroup(8, hourly_weather[8]['temp'] ,ICON_MAP.index(hourly_weather[8]["weather"][0]["icon"][:2]), x=180, y=95)
        display_group.append(nextHourGroup)

        nextDayGroup = displayio.Group(max_size=4, x=220, y=93)

        nextDayIcon = displayio.TileGrid(
            icons_small_bmp,
            pixel_shader=icons_small_pal,
            x=25,
            y=10,
            width=1,
            height=1,
            tile_width=20,
            tile_height=20,
        )
        nextDayIcon[0] = ICON_MAP.index(daily_weather[1]['weather'][0].get('icon')[:2])
        nextDayGroup.append(nextDayIcon)

        nextDayMinLabel = label.Label(font_small, text="-99.9", color=0x000000)
        nextDayMinLabel.text = "{:2.1f}".format(nextDayMin)
        nextDayMinLabel.anchor_point = (1.0, 0.0)
        nextDayMinLabel.anchored_position = (24, 15)
        nextDayGroup.append(nextDayMinLabel)

        nextDayMaxLabel = label.Label(font_small, text="-99.9", color=0x000000)
        nextDayMaxLabel.text = "{:4.1f}".format(nextDayMax)
        nextDayMaxLabel.anchor_point = (0.0, 0.0)
        nextDayMaxLabel.anchored_position = (46, 15)
        nextDayGroup.append(nextDayMaxLabel)

        tomorrowLabel = label.Label(font_small, text="Tomorrow", color=0x000000)
        tomorrowLabel.text = DAYS[time.localtime(daily_weather[1]['dt']).tm_wday]
        tomorrowLabel.anchor_point = (0.5, 1.0)
        tomorrowLabel.anchored_position = (35, 9)
        nextDayGroup.append(tomorrowLabel)

        display_group.append(nextDayGroup)

        # Show everything
        print("Showing display")
        display.refresh()

    else:
        print("It was too dark")

# If anything goes wrong sleep for 30 seconds and try again
except:
    print("*****")
    print("Unexpected error")
    print("*****")
    import alarm
    pause = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + 30)
    alarm.exit_and_deep_sleep_until_alarms(pause)

# Sleep for 5 minutes
import alarm
pause = alarm.time.TimeAlarm(monotonic_time=time.monotonic() + 300)
alarm.exit_and_deep_sleep_until_alarms(pause)

while True:
    pass
