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

DEBUG = True
def log(*args, **kwargs):
    if DEBUG:
        print("[NEWS]", *args, **kwargs)


def convert_time_by_offset(input_time, offset_str, target_offset_str):
    try:
        try:
            input_time_obj = datetime.strptime(input_time.strip(), '%I:%M%p')
        except ValueError:
            input_time_obj = datetime.strptime(input_time.strip(), '%H:%M')

        input_offset_hours = _parse_utc_offset_hours(offset_str)
        target_offset_hours = _parse_utc_offset_hours(target_offset_str)

        input_timezone = pytz.FixedOffset(input_offset_hours * 60)
        target_timezone = pytz.FixedOffset(target_offset_hours * 60)

        localized_input_time = input_timezone.localize(input_time_obj)
        converted_time = localized_input_time.astimezone(target_timezone)
        return converted_time.strftime('%H:%M')
    except Exception:
        return input_time


async def write_json(filepath, filecontent):
    async with aiofiles.open(filepath, mode='w') as file:
        await file.write(json.dumps(filecontent, indent=4))

# EMOJIS


def form_emoji(impact_color):
    if impact_color == "gray" or impact_color == "grey":
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

# TIMEZONE


async def set_user_timezone(timezone_name, offset, channel):
    async with aiofiles.open('database.json', mode='r') as file:
        existing_data = await file.read()
    if existing_data:
        data = json.loads(existing_data)
    else:
        data = {}
    data['timezone'] = {"name": timezone_name, "offset": offset}
    await write_json('database.json', data)
    tz = pytz.timezone(timezone_name)
    now = datetime.now(tz)
    _ = await convert_timezone_and_create_csv()
    await channel.send(
        f"Your timezone has been set to {timezone_name}.\nCurrent date and time: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    await convert_timezone_and_create_csv()

def find_timezone_name_using_offset(offset_str):
    try:
        offset = _parse_utc_offset_hours(offset_str)  # supports 'UTC'
    except ValueError:
        return False, "Invalid offset. Please use formats like 'UTC', 'UTC+5' or 'UTC-3'."

    # Find any timezone currently matching that offset (respects DST)
    wanted = f'{offset:+03d}00'
    for tz in TIMEZONES:
        try:
            if datetime.now(pytz.timezone(tz)).strftime('%z') == wanted:
                return tz, "Done"
        except Exception:
            continue
    return False, "No timezone found for the specified offset."

async def get_timezones():
    async with aiofiles.open('database.json', mode='r') as file:
        database = await file.read()
    database = json.loads(database)
    main_timezone = database["timezone"]
    scraped_timezone = database["timezone_scraped"]
    return main_timezone, scraped_timezone

# DATABASE


async def get_database():
    async with aiofiles.open('database.json', mode='r') as file:
        database = await file.read()
    database = json.loads(database)
    return database

# SET UPDATE STATUS


async def update_status():
    database = await get_database()
    database['updated'] = True
    await write_json('database.json', database)

# RESET UPDATE STATUS


async def reset_update_status():
    database = await get_database()
    database['updated'] = False
    await write_json('database.json', database)


def get_datetime_by_offset(offset_str):
    try:
        offset_hours = _parse_utc_offset_hours(offset_str)
        total_offset_minutes = offset_hours * 60
        current_utc_time = datetime.now(pytz.utc)
        return current_utc_time + timedelta(minutes=total_offset_minutes)
    except ValueError:
        return None


async def convert_timezone_and_create_csv():
    main_timezone, scraped_timezone = await get_timezones()
    current_date = datetime.now()

    # Get month and year dynamically
    month = current_date.strftime('%B')
    year = current_date.strftime('%Y')

    # Input and output paths now include the year
    input_csv_path = f"news/{month}_{year}_news.csv"
    output_csv_path = f"news/{month}_{year}_converted.csv"

    # Read input CSV asynchronously via thread
    df = await asyncio.to_thread(pd.read_csv, input_csv_path)

    main_timezone_offset = main_timezone["offset"]
    scraped_timezone_offset = scraped_timezone["offset"]

    # Preserve behavior: store offset string in the column
    df["timezone"] = main_timezone["offset"]

    # ---- handle new/old time + date formats ----
    for index, row in df.iterrows():
        # TIME: convert from scraped -> main timezone; accept 12h or 24h
        try:
            time_str = str(row['time'])
            time_converted = convert_time_by_offset(
                time_str, scraped_timezone_offset, main_timezone_offset
            )
            df.at[index, "time"] = time_converted
        except Exception:
            pass  # keep original if anything odd

        # DATE: accept 'DD/MM/YYYY' (new) or '%b %d' (old); output 'YYYY-MM-DD'
        date_str = str(row['date']).strip()
        try:
            if "/" in date_str:
                # New format: 02/09/2025
                date_obj = datetime.strptime(date_str, '%d/%m/%Y')
            else:
                # Old format: 'Sep 02' -> add current year
                date_obj = datetime.strptime(date_str, '%b %d')
                date_obj = date_obj.replace(year=current_date.year)
            df.at[index, 'date'] = date_obj.strftime('%Y-%m-%d')
        except Exception:
            # If parsing fails, leave date as-is (backwards compatible)
            pass

    if '10min_update_sent' not in df.columns:
        df['10min_update_sent'] = False

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
    datetime_obj = get_datetime_by_offset(offset)
    time_str = datetime_obj.time().strftime('%H:%M')
    return datetime_obj.time(), time_str

async def news_today(client, df, message, channel_id):
    try:
        database = await get_database()
        impacts = database['impacts']
        currencies = database['currencies']
        main_timezone = database['timezone']
        main_timezone_offset = main_timezone["offset"]
        datetime_obj = get_datetime_by_offset(main_timezone_offset)
        today_date = datetime_obj.date()

        log(f"Timezone: {main_timezone} | Today: {today_date} | Impacts: {impacts} | Currencies: {currencies}")
        # show how many rows match the date string
        date_str = str(today_date)
        df_today = df[df['date'] == date_str]
        log(f"Rows with date == {date_str}: {len(df_today)}")

        todays_events = ""
        for index, row in df_today.iterrows():
            try:
                event_date = datetime.strptime(row["date"], '%Y-%m-%d').date()
            except ValueError as e:
                log(f"[row {index}] bad date '{row.get('date')}' ({e})")
                continue

            if row['currency'] in currencies and row['impact'] in impacts and event_date == today_date:
                log(f"[MATCH] {row['date']} {row['time']} {row['currency']} {row['impact']} {row['event']}")
                todays_events += f"{form_emoji(row['impact'])} {form_emoji_flag(row['currency'])} {row['currency']} **{row['time']}** - {row['event']}\n"
            else:
                log(f"[SKIP] {row['date']} {row['time']} {row['currency']} {row['impact']}  "
                    f"(in currencies? {row['currency'] in currencies}, in impacts? {row['impact'] in impacts})")

        if todays_events:
            if message:
                await message.channel.send(todays_events)
            else:
                await client.get_channel(channel_id).send(todays_events)
            log("Sent today's events.")
        else:
            news = f"No News for today {today_date}"
            if message:
                await message.channel.send(news)
            else:
                await client.get_channel(channel_id).send(news)
            log("No events matched filters for today.")

    except Exception as e:
        log(f"news_today ERROR: {e}")



def is_red_impact(impact):
    return impact.lower() == "red"


def is_orage_impact(impact):
    return impact.lower() == "orange"


async def filter_df_for_today(df):
    database = await get_database()
    main_timezone = database['timezone']
    main_timezone_offset = main_timezone["offset"]
    datetime_obj = get_datetime_by_offset(main_timezone_offset)
    today_date = datetime_obj.date()
    filter = df.query(f'date=="{str(today_date)}"')
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
            await news_today(client, df, message=None, channel_id=channel_id)
            await update_status()
            return
        if updated and str(current_time.hour) == str(int(daily_updates['hour'])+2):
            await reset_update_status()
            return
    except Exception as e:
        print("Got Error in daily updates block", str(e))

    news = ""
    filtered_df = await filter_df_for_today(df)
    try:
        for index, row in filtered_df.iterrows():
            if row['impact'] in impacts and row['currency'] in currencies:
                try:
                    event_date = datetime.strptime(
                        row["date"], '%Y-%m-%d').date()
                except ValueError:
                    print(
                        f"Cannot read event date for row {index}: time: {row[1]}")
                    continue  # Skip this row if date parsing fails()

                if ":" not in row["time"]:
                    continue

                # Check if time format is "HH:MM"
                event_time_parts = row["time"].split(":")
                if len(event_time_parts) != 2:
                    continue
                hour = int(event_time_parts[0])
                minute = int(event_time_parts[1])

                # Avoid importing datetime.time (to keep your other imports untouched):
                event_time = f"{hour:02d}:{minute:02d}"

                current_time_obj, current_time_str = await get_current_time()
                current_time_plus_10_min = (
                    (datetime.now().replace(hour=current_time_obj.hour, minute=current_time_obj.minute, second=0, microsecond=0)
                     + timedelta(minutes=587))  # keeping your original offset logic
                    .strftime("%H:%M")
                )
                row_list = row.tolist()

                if json.dumps(row_list) not in database['updated_rows']:
                    if event_time == current_time_plus_10_min:
                        if is_red_impact(row['impact']) or is_orage_impact(row['impact']):
                            news += f"{form_emoji(row['impact'])} {form_emoji_flag(row['currency'])} {row['currency']} **{row['time']}** - {row['event']}\n"
                            database['updated_rows'].append(
                                json.dumps(row_list))
                            async with aiofiles.open('database.json', mode='w') as file:
                                await file.write(json.dumps(database), indent=4)

        if news:
            await client.get_channel(channel_id).send(news)

    except Exception as e:
        print(str(e))


def _parse_utc_offset_hours(offset_str: str) -> int:
    """
    Parse strings like 'UTC', 'UTC+0', 'UTC-0', 'UTC+5', 'UTC-12' -> integer hours.
    Raises ValueError if the format is invalid.
    """
    s = offset_str.strip().upper()
    if not s.startswith('UTC'):
        raise ValueError("Offset must start with 'UTC'")
    rest = s[3:]  # after 'UTC'
    if rest == '' or rest in ('+0', '-0'):
        return 0
    # Allow forms like 'UTC+5' / 'UTC-3'
    sign = rest[0]
    if sign in ('+', '-'):
        num = int(rest[1:])
        return num if sign == '+' else -num
    # Fallback: 'UTC5' (not recommended, but handle)
    return int(rest)
