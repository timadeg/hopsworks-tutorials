# Imports
import requests
import datetime
import time
import pandas as pd
import hopsworks


def model(dbt, session):
    # Setup cluster usage
    dbt.config(
        submission_method="cluster",
        dataproc_cluster_name="{YOUR_DATAPROC_CLUSTER_NAME}",
    )

    # Read data_pipeline Python model
    data_pipeline = dbt.ref("data_pipeline")

    print('📊 Parsing starts...')


    def get_weather_data_from_open_meteo(
        city_name: str,
        coordinates: list,
        start_date: str,
        end_date: str = None,
        forecast: bool = True
    ):
        """
        Takes city name, coordinates and returns pandas DataFrame with weather data.
        
        Examples of arguments:
            coordinates=(47.755, -122.2806), start_date="2023-01-01"
        """
        start_of_cell = time.time()
        
        if not end_date:
            end_date = start_date
        
        latitude, longitude = coordinates
        
        params = {
            'latitude': latitude,
            'longitude': longitude,
            'hourly': ["temperature_2m",
                    "relativehumidity_2m",
                    "weathercode",
                    "windspeed_10m",
                    "winddirection_10m",
                    ],
            'start_date': start_date,
            'end_date': end_date,
            'timezone': "Europe/London"
        }

        base_url = 'https://api.open-meteo.com/v1/forecast' 
            
        try:
            response = requests.get(base_url, params=params)
        except ConnectionError:
            base_url = 'https://archive-api.open-meteo.com/v1/archive' 
            response = requests.get(base_url, params=params)
        
        response_json = response.json()    
        res_df = pd.DataFrame(response_json["hourly"])
        
        # rename columns
        res_df = res_df.rename(columns={
            "time": "base_time",
            "temperature_2m": "temperature",
            "weathercode": "weather_code",
            "relativehumidity_2m": "relative_humidity",
            "windspeed_10m": "wind_speed",
            "winddirection_10m": "wind_direction"
        })
        
        # change columns order
        res_df = res_df[
            ['base_time',
            'temperature',
            'relative_humidity',
            'weather_code',
            'wind_speed',
            'wind_direction']
        ]
        
        # convert dates in 'date' column
        res_df["base_time"] = pd.to_datetime(res_df["base_time"])
        res_df['city_name'] = city_name
        res_df['forecast_hr'] = 0
        
        end_of_cell = time.time()
        print(f"Parsed weather for {city_name} since {start_date} till {end_date}.")
        print(f"Took {round(end_of_cell - start_of_cell, 2)} sec.\n")
            
        return res_df


    city_coords = {
        "London": [51.51, -0.13],
        "Paris": [48.85, 2.35],
        "Stockholm": [59.33, 18.07],
        "New York": [40.71, -74.01],
        "Los Angeles": [34.05, -118.24],
        "Singapore": [1.36, 103.82],
        "Sydney": [-33.87, 151.21],
        "Hong Kong": [22.28, 114.16],
        "Rome": [41.89, 12.48],
        "Kyiv": [50.45, 30.52]
    }

    # Parse and insert updated data from observations endpoint
    parsed_df = pd.DataFrame()

    for city_name, city_coord in city_coords.items():
        weather_df_temp = get_weather_data_from_open_meteo(
            city_name,
            city_coord,
            '2023-06-05',
        )
        parsed_df = pd.concat([parsed_df, weather_df_temp])

    # Perform feature engineering
    parsed_df['index_column'] = parsed_df.index
    parsed_df['hour'] = parsed_df['base_time'].dt.hour
    parsed_df['day'] = parsed_df['base_time'].dt.day
    parsed_df['temperature_diff'] = parsed_df.groupby('city_name')['temperature'].diff()
    parsed_df['wind_speed_category'] = pd.cut(
        parsed_df['wind_speed'],
        bins=[0, 2.5, 5.0, 7.5, float('inf')],
        labels=['Low', 'Moderate', 'High', 'Very High']
    ).astype(str)

    parsed_df[[
        'city_name',
        'base_time',
        'forecast_hr',
        'temperature',
        'relative_humidity',
        'weather_code',
        'wind_speed',
        'wind_direction',
        'index_column',
        'hour',
        'day',
        'temperature_diff',
        'wind_speed_category',
    ]].head(3)

    print('✅ Parsing finished successfully!!!🎉')

    # Login to your Hopsworks project
    project = hopsworks.login(
        host="{YOUR_HOST}",          
        project="{YOUR_PROJECT_NAME}",
        api_key_value="{YOUR_HOPSWORKS_API_KEY}"
    )

    # Get feature Store
    fs = project.get_feature_store() 

    # Retrieve required Feature Group
    feature_group = fs.get_or_create_feature_group(
        name = '{YOUR_FEATURE_GROUP_NAME}',
        version = 1,
    )    

    # Insert data into Feature Group
    feature_group.insert(parsed_df)   

    return parsed_df