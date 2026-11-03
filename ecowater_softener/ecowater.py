import ayla_iot_unofficial, datetime, time

from .const import (
    APP_ID,
    APP_SECRET,
    UPDATE_PROPERTY,
    SALT_TENTHS_MAX
)

class EcowaterDevice(ayla_iot_unofficial.device.Device):
    def update(self, property_list = None):
        data = super(EcowaterDevice, self).update(property_list)
        
        # If data hasn't been updated in the last 5 mins then tell the device to update the data and wait 30 secs for the device to update the data
        last_updated = datetime.datetime.strptime(self.properties_full["gallons_used_today"]["data_updated_at"], "%Y-%m-%dT%H:%M:%SZ")
        last_updated = last_updated.replace(tzinfo=datetime.timezone.utc)
        current_time = datetime.datetime.now(datetime.timezone.utc)
        five_minutes_ago = current_time - datetime.timedelta(minutes=5)

        if last_updated < five_minutes_ago:
            self.ayla_api.self_request('post', self.set_property_endpoint(UPDATE_PROPERTY), json={'datapoint': {'value': 1}})
            time.sleep(30)
            data = super(EcowaterDevice, self).update(property_list)
        
        return data

    # Device Info
    @property
    def model(self) -> str:
        return self.get_property_value('model_description')
    
    @property
    def software_version(self) -> str:
        return self.get_property_value("base_software_version")

    @property
    def ip_address(self) -> str:
        return self._device_ip_address

    @property
    def rssi(self) -> int:
        return self.get_property_value("rf_signal_strength_dbm")

    # Water
    
    @property
    def water_use_avg_daily(self) -> int:
        return self.get_property_value("avg_daily_use_gals")
    
    @property
    def water_use_today(self) -> int:
        return self.get_property_value("gallons_used_today")
    
    @property
    def water_available(self) -> int:
        return self.get_property_value("treated_water_avail_gals")
    
    @property
    def water_total_counter(self) -> int:
        return self.get_property_value("water_counter_gals")

    # Water flow

    @property
    def current_water_flow(self) -> float:
        return self.get_property_value("current_water_flow_gpm") / 10

    # Salt

    @property
    def salt_level_percentage(self) -> float:
        return (self.get_property_value("salt_level_tenths") * 100) / SALT_TENTHS_MAX[str(self.get_property_value("model_id"))]
    
    @property
    def out_of_salt_days(self) -> int:
        return self.get_property_value("out_of_salt_estimate_days")
    
    @property
    def out_of_salt_date(self) -> datetime.date:
        return datetime.datetime.now().date() + datetime.timedelta(days = self.get_property_value("out_of_salt_estimate_days"))
    
    @property
    def salt_type(self) -> str:
        if self.get_property_value("salt_type_enum") == 0:
            return "NaCl"
        else:
            return "KCl"
    
    # Rock

    @property
    def rock_removed_avg_daily(self) -> float:
        return self.get_property_value("daily_avg_rock_removed_lbs") /10000

    @property
    def rock_removed(self) -> float:
        return self.get_property_value("total_rock_removed_lbs") / 10
    
    # Ion exchange capacity
    @property
    def ion_operating_capacity(self) -> int:
        return self.get_property_value("operating_capacity_grains")

    @property
    def ion_capacity_remaining(self) -> int:
        return self.get_property_value("capacity_remaining_percent") / 10.0

    @property
    def ion_average_exhaustion(self) -> int:
        return (1000 - self.get_property_value("average_exhaustion_percent")) / 10.0

    # Recharge
    @property
    def recharge_status(self) -> str:
        if self.get_property_value("regen_status_enum") == 0:
            return "None"
        elif self.get_property_value("regen_status_enum") == 1:
            return "Scheduled"
        else:
            return "Recharging"

    @property
    def recharge_enabled(self) -> bool:
        return self.get_property_value("regen_enable_enum") == 1
    
    @property
    def recharge_scheduled(self) -> bool:
        return self.get_property_value("regen_status_enum") == 1
    
    @property
    def recharge_recharging(self) -> bool:
        return self.get_property_value("regen_status_enum") == 2

    @property
    def last_recharge_days(self) -> int:
        return self.get_property_value("days_since_last_regen")
    
    @property
    def last_recharge_date(self) -> datetime.date:
        # The device bumps the counter around midday, so count from the counter's own update date, not today
        return self._property_updated_at("days_since_last_regen").astimezone().date() - datetime.timedelta(days = self.get_property_value("days_since_last_regen"))

    @property
    def recharge_time(self) -> datetime.time:
        secs = self.get_property_value("regen_time_secs")
        return datetime.time(secs // 3600, secs % 3600 // 60)

    @property
    def next_recharge_time(self) -> datetime.datetime:
        # Uses the device clock (current_time_secs at its update moment), so no timezone guessing is needed
        secs_until = (self.get_property_value("regen_time_secs") - self.get_property_value("current_time_secs")) % 86400
        next_time = self._property_updated_at("current_time_secs") + datetime.timedelta(seconds = secs_until)
        return next_time.replace(second = 0) + datetime.timedelta(minutes = round(next_time.second / 60))

    def schedule_recharge(self) -> None:
        # The device recharges at its next recharge time
        self._set_regen_status(1)

    def recharge_now(self) -> None:
        self._set_regen_status(2)

    def _set_regen_status(self, value: int) -> None:
        self.ayla_api.self_request('post', self.set_property_endpoint("regen_status_enum"), json={'datapoint': {'value': value}})

    def _property_updated_at(self, name: str) -> datetime.datetime:
        updated_at = datetime.datetime.strptime(self.properties_full[name]["data_updated_at"], "%Y-%m-%dT%H:%M:%SZ")
        return updated_at.replace(tzinfo = datetime.timezone.utc)


class EcowaterAccount:
    def __init__(self, username: str, password: str) -> None:
        self.ayla_api = ayla_iot_unofficial.new_ayla_api(username, password, APP_ID, APP_SECRET)
        self.ayla_api.sign_in()

    def get_devices(self) -> list:
        devices = self.ayla_api.get_devices()

        # Filter for Ecowater devices
        devices = list(filter(lambda device: device._oem_model_number.startswith("EWS"), devices))

        # Convert devices to EcowaterDevice Class
        for device in devices:
            setattr(device, "__class__", EcowaterDevice)

        return devices
