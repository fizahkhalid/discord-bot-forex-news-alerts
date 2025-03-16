import json
import requests
import asyncio
import aiofiles
import pytz
from utils import (
    find_timezone_name_using_offset,
    set_user_timezone,
    get_database,
    form_emoji,
    write_json,
    get_datetime_by_offset)

### SEND RANDOM QUOTE
async def send_qoute(message):
  response = requests.get('https://zenquotes.io/api/random')
  json_data = json.loads(response.text)
  quote = json_data[0]['q'] + " - " + json_data[0]['a']
  await message.channel.send(quote)
  return (quote)

async def handle_timezone_message(client,message):
  select_timezone = "Please select timezone from UTC-12 to UTC+14"
  await message.channel.send(select_timezone)

  def check(m):
    return m.author == message.author and m.channel == message.channel and m.content.strip().startswith('UTC')
  try:
    reply = await client.wait_for('message', timeout=60.0, check=check)

  except asyncio.TimeoutError:
    await message.channel.send("Sorry, you took too long to reply.")
  else:
    timezone_name, message_for_timezone = find_timezone_name_using_offset(reply.content)
    if not timezone_name:
      await set_user_timezone(timezone_name, reply.content,message.channel)
    else:
      await message.channel.send(message_for_timezone)


async def state(message):
    database = await get_database()
    message_str = f"*FILTER*\n"
    message_str += f"**Currencies:** `{' | '.join(database['currencies'])}`\n"
    message_str += f"**Impacts:** `{' | '.join(database['impacts'])}`\n\n"
    message_str += f"*DAILY UPDATES*\n"
    message_str += f"**Status:** `{database['updated']}`\n"
    message_str += f"**Time:** `{database['daily_update']['hour']}`:`{database['daily_update']['minute']}`\n\n"
    
    message_str += f"*ALERTS*\n"
    message_str += f"**Time difference for Alerts:** `{database['time_threshold']} minutes`\n"
    message_str += f"**Timezone Offset:** `{database['timezone']['offset']}`\n"
    await message.channel.send(message_str)


async def handle_datetime_command(message):
    existing_data = await get_database()
    if existing_data=={}:
       await message.channel.send(f"Database is empty !")
    else:
       data = existing_data
       
    if 'timezone' in data.keys():
        timezone_dict = data['timezone']
        offset = timezone_dict['offset']

        datetime = get_datetime_by_offset(offset)
        time = datetime.time().strftime('%H:%M')

        tz = pytz.timezone(timezone_dict['name'])
        now = datetime.now(tz)
        timezoneOffset = timezone_dict['offset']
    else:
        now = datetime.now()
        timezoneOffset = None
    # send the confirmation message with the current date and time
    await message.channel.send(f"Date: `{now.strftime('%d-%m-%Y')}`\nTime: `{time}`\nTimezone: `{timezoneOffset}`")
    
async def set_allowed_currencies(message):
    msg = message.content
    database = await  get_database()
    currencies = msg.split(":")[-1]
    if currencies.lower().strip() == "all":
        filtered = database['all_currencies']
    else:
        filtered = []
        currencies = currencies.split(",")
        for currency in currencies:
            if currency in database['all_currencies']:
                filtered.append(currency)
    
    database['currencies'] = filtered
    await write_json('database.json',database)
    await message.channel.send(f"Updated Currencies Filter to Include these currencies: {filtered}")

async def set_allowed_impacts(message): 
    impacts = message.content.split("impacts:")[-1].split(",")
    print("Impacts: ",impacts)
    if impacts!=['']:
        database = await get_database()
        database['impacts'] = impacts
        await write_json('database.json',database)
        await message.channel.send(f"Updated Impacts Filter to Include these impacts: {'-'.join([form_emoji(impact) for impact in impacts])}")
    else:
        await message.channel.send("You are trying to set empty impacts, it cannot be empty")


async def set_daily_update_time(message):
    update_time = message.content.split(":")
    
    if len(update_time) == 3:
        hour = update_time[-2].zfill(2)  # Ensure two-digit hour format
        minute = update_time[-1].zfill(2)  # Ensure two-digit minute format
        
        # Check if hour and minute are valid integers
        if hour.isdigit() and minute.isdigit():
            hour = int(hour)
            minute = int(minute)
            
            # Check if hour and minute are within valid ranges (0-23 for hour, 0-59 for minute)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                database = await get_database()
                database["daily_update"]["hour"] = str(hour)
                database["daily_update"]["minute"] = str(minute)
                await write_json('database.json',database)
                await message.channel.send(f"News Daily Update Time changed to {hour:02d}:{minute:02d}")
            else:
                await message.channel.send("Invalid hour or minute value. Hour should be between 0 and 23, and minute should be between 0 and 59.")
        else:
            await message.channel.send("Invalid hour or minute format. Please use two-digit format, e.g., !daily:03:03")
    else:
        await message.channel.send("Invalid command format. Please use !daily:hh:mm")