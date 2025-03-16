import time
import json
import asyncio
import aiofiles
import pytz
import pandas as pd
from datetime import datetime
from discord.ext import tasks
from datetime import timedelta
from data import TIMEZONES

def convert_time_by_offset(input_time, offset_str, target_offset_str):
    try:
        input_time_obj = datetime.strptime(input_time, '%I:%M%p')
        input_offset_hours = int(offset_str.split('UTC')[1])
        target_offset_hours = int(target_offset_str.split('UTC')[1])
        input_timezone = pytz.FixedOffset(input_offset_hours * 60)
        target_timezone = pytz.FixedOffset(target_offset_hours * 60)
        localized_input_time = input_timezone.localize(input_time_obj)
        converted_time = localized_input_time.astimezone(target_timezone)

        return converted_time.strftime('%H:%M')
    except ValueError:
        return input_time
    except pytz.UnknownTimeZoneError:
        return "Invalid offset or timezone"

async def write_json(filepath, filecontent):
    async with aiofiles.open(filepath, mode='w') as file:
        await file.write(json.dumps(filecontent,indent=4))


### EMOJIS
def form_emoji(impact_color):
    if impact_color == "gray" or impact_color=="grey":
        impact_color = "white"
    return f":{impact_color}_circle:"

def form_emoji_flag(currency):
    # Define a dictionary mapping currency codes to flag emojis
    flag_mapping = {
        "USD": ":flag_us:",
        "AUD": ":flag_au:",
        "CAD": ":flag_ca:",
        "CHF": ":flag_ch:",
        "CNY": ":flag_cn:",
        "EUR": ":flag_eu:",
        "GBP": ":flag_gb:",
        "JPY": ":flag_jp:",
        "NZD": ":flag_nz:",
    }
    return flag_mapping.get(currency, "")
    
### TIMEZONE
async def set_user_timezone(timezone_name, offset, channel):
    async with aiofiles.open('database.json', mode='r') as file:
        existing_data = await file.read()
    if existing_data:
        data = json.loads(existing_data)
    else:
        data = {}
    data['timezone'] = {"name": timezone_name, "offset": offset}
    await write_json('database.json',data)
    tz = pytz.timezone(timezone_name)
    now = datetime.now(tz)
    _ = await convert_timezone_and_create_csv()
    await channel.send(
  f"Your timezone has been set to {timezone_name}.\nCurrent date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    await convert_timezone_and_create_csv()
    
def find_timezone_name_using_offset(offset_str):
    try:
        number = offset_str.split("UTC")[-1][1::]
        sign = offset_str.split("UTC")[-1][0]
        offset = int(number)
        if sign == "-":
          offset = -1*offset
        elif sign == "+":
          offset = offset
        else:
          return False,"Invalid Format, Kindly Enter Timezone In this format [UTC+12 or UTC-5]"
    except ValueError:
        return False,"Invalid offset. Please use this format 'UTC-offset'."
    for tz in TIMEZONES:
        if datetime.now(pytz.timezone(tz)).strftime('%z') == f'{offset:+03d}00':
            return tz, "Done"
    return False, "No timezone found for the specified offset."



async def get_timezones():
    async with aiofiles.open('database.json', mode='r') as file:
        database = await file.read() 
    database = json.loads(database)
    main_timezone = database["timezone"]
    scraped_timezone = database["timezone_scraped"]
    return main_timezone,scraped_timezone

### DATABASE
async def get_database():
    async with aiofiles.open('database.json', mode='r') as file:
        database = await file.read()
    database = json.loads(database)
    return database

### SET UPDATE STATUS
async def update_status():
    database = await get_database()
    database['updated'] = True
    await write_json('database.json',database)

### RESET UPDATE STATUS
async def reset_update_status():
    database = await get_database()
    database['updated'] = False
    await write_json('database.json',database)


def get_datetime_by_offset(offset_str):
    try:
        # Parse the offset string, e.g., 'UTC+5' or 'UTC-3'
        offset_hours = int(offset_str.split('UTC')[1])

        # Calculate the total offset in minutes
        total_offset_minutes = offset_hours * 60

        # Get the current time in UTC
        current_utc_time = datetime.now(pytz.utc)

        # Calculate the datetime for the specified offset
        target_datetime = current_utc_time + timedelta(minutes=total_offset_minutes)

        return target_datetime
    except ValueError:
        # Handle invalid offset format
        return None
    
async def convert_timezone_and_create_csv():
    main_timezone, scraped_timezone = await get_timezones()
    current_date = datetime.now()
    month = current_date.strftime('%B')
    input_csv_path = f"news/{month}_news.csv"
    output_csv_path = f"news/{month}_converted.csv"
    df = await asyncio.to_thread(pd.read_csv, input_csv_path)

    main_timezone_offset = main_timezone["offset"]
    scraped_timezone_offset = scraped_timezone["offset"]

    df["timezone"] = main_timezone["offset"]

    for index, row in df.iterrows():
        # Check if the 'time' column contains a valid time
        try:
            time_str = row['time']
            time_converted = convert_time_by_offset(time_str,scraped_timezone_offset,main_timezone_offset)
            df.at[index, "time"] = time_converted
        except ValueError:
            # Skip rows with invalid time format
            pass

        # Parse and format the 'date' column
        date_str = row['date']
        date_obj = datetime.strptime(date_str, '%b %d')
        date_obj = date_obj.replace(year=current_date.year)
        df.at[index, 'date'] = date_obj.strftime('%Y-%m-%d')

    if '10min_update_sent' not in df.columns:
        # Add a new column to track update status
        df['10min_update_sent'] = False
        
    # Save the modified DataFrame to a new CSV file asynchronously
    await asyncio.to_thread(df.to_csv, output_csv_path, index=False)
    return df



async def get_current_time():
    existing_data = await get_database()
    if not existing_data:
        return False
    
    if 'timezone' not in existing_data.keys():
        return False
    
    timezone_dict = existing_data['timezone']
    offset = timezone_dict['offset']
    datetime = get_datetime_by_offset(offset)
    time = datetime.time().strftime('%H:%M')
    return datetime.time(),time

async def news_today(client, df, message,channel_id):
    try:
        database = await get_database()
        impacts = database['impacts']
        currencies = database['currencies']
        main_timezone = database['timezone']
        main_timezone_offset = main_timezone["offset"]
        datetime = get_datetime_by_offset(main_timezone_offset)
        today_date = datetime.date()

        todays_events = ""
        filter =  df.query(f'date=="{str(today_date)}"')
        for index, row in filter.iterrows():
            #print("row",row)
            try:
                event_date = datetime.strptime(row["date"], '%Y-%m-%d').date()
            except ValueError as e:
                print("here")
                print(f"Cannot read event date for row {index}: time: {row[1]}",str(e))
                continue  # Skip this row if date parsing fails

            if row['currency'] in currencies and row['impact'] in impacts and event_date == today_date:
                todays_events += f"{form_emoji(row['impact'])} {form_emoji_flag(row['currency'])} {row['currency']} **{row['time']}** - {row['event']}\n"

        if todays_events:
            if message:
                await message.channel.send(todays_events)
            else:
                await client.get_channel(channel_id).send(todays_events)
        else:
            news = f"No News for today {today_date}"
            if message:
                await message.channel.send(news)
            else:
                await client.get_channel(channel_id).send(news)
    except Exception as e:
        print(f"Got Error {str(e)}")


def is_red_impact(impact):
    return impact.lower() == "red"

def is_orage_impact(impact):
    return impact.lower() == "orange"


async def filter_df_for_today(df):
    database = await get_database()
    main_timezone = database['timezone']
    main_timezone_offset = main_timezone["offset"]
    datetime = get_datetime_by_offset(main_timezone_offset)
    today_date = datetime.date()
    filter =  df.query(f'date=="{str(today_date)}"')
    return filter

async def news_updates(client, df, channel_id):
    database = await get_database()
    if 'updated_rows' not in database.keys():
        database['updated_rows'] = []
    main_timezone = database['timezone']
    main_timezone_name = main_timezone["name"]
    impacts = database['impacts']
    currencies = database['currencies']

    current_time = datetime.now(pytz.timezone(main_timezone_name))
    updated = database['updated']
    daily_updates = database['daily_update']


    if main_timezone_name != df["timezone"].tolist()[0]:
        df = await convert_timezone_and_create_csv()
    else:
        print("Timezone is correct")

    try:
        if not updated and str(current_time.hour) == daily_updates['hour'] and str(current_time.minute) == daily_updates['minute']:
            await news_today(client,df,message=None, channel_id=channel_id)
            await update_status()
            return
        if updated and str(current_time.hour) == str(int(daily_updates['hour'])+2):
            await reset_update_status()
            return
    except Exception as e:
        print("Got Error in daily updates block",str(e))
    
    news = ""
    filtered_df = await filter_df_for_today(df)
    try:
        for index, row in filtered_df.iterrows():
            if row['impact'] in impacts and row['currency'] in currencies:
                try:
                    event_date = datetime.strptime(row["date"], '%Y-%m-%d').date()

                except ValueError:
                    print(f"Cannot read event date for row {index}: time: {row[1]}")
                    continue  # Skip this row if date parsing fails()

                if ":" not in row["time"]:
                    continue
               
                # Check if time format is "HH:MM"
                event_time_parts = row["time"].split(":")
                if len(event_time_parts)!=2:
                    continue
                hour = int(event_time_parts[0])
                minute = int(event_time_parts[1])
                event_time = time(hour, minute).strftime("%H:%M")
                        
                curernt_time, current_time_str = await get_current_time()
                current_time_plus_10_min = (current_time + timedelta(minutes=587)).strftime("%H:%M")
                row_list = row.tolist()

                if json.dumps(row_list) not in database['updated_rows']:    
                    if event_time == current_time_plus_10_min:
                        if is_red_impact(row['impact']) or is_orage_impact(row['impact']):
                            news += f"{form_emoji(row['impact'])} {form_emoji_flag(row['currency'])} {row['currency']} **{row['time']}** - {row['event']}\n"
                            database['updated_rows'].append(json.dumps(row_list))
                            async with aiofiles.open('database.json', mode='w') as file:
                                await file.write(json.dumps(database),indent=4)
                            
        if news:
            await client.get_channel(channel_id).send(news)


    except Exception as e:
        print(str(e))