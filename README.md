# Dahua/Lorex RPC Control for Home Assistant

A high-performance, asynchronous custom integration for Home Assistant designed to provide granular control over Dahua, Lorex, and Amcrest cameras/NVRs using their native **JSON-RPC** protocol.

Unlike standard integrations that rely solely on ONVIF, this integration allows you to manipulate deep system settings—such as siren durations, lighting schemes, and AI scene profiles—directly from your Home Assistant dashboard.

---

## 🛠 Features

* **⚡️ Advanced Siren Control:** Includes a "Smart Siren" feature that can override the default camera duration (e.g., set to 10 minutes) and automatically restore your original settings once silenced.
* **💡 Lighting & Night Vision Management:** Toggle white light LEDs (Coaxial Control) and switch between Infrared, White Light, or AI illumination modes.
* **🤖 AI Scene Switching:** Manually or automatically switch between "Day," "Night," and "Auto" profiles to optimize image quality based on environmental conditions.
* **📡 Real-Time Synchronized States:** Polls the camera every 10 seconds to ensure the Home Assistant UI accurately reflects the camera's internal state.
* **📸 Lightweight Snapshot Engine:** A dedicated snapshot API handler that supports both Digest and Basic authentication for dashboard previews.
* **🔒 Thread-Safe Communication:** Uses an RLock mechanism to queue commands, preventing "too many connections" errors that often crash camera web servers.

---

## 🚀 Installation

### Option 1: Via HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Click the **three dots** in the top right and select **Custom repositories**.
3. Add the URL of this repository with the category **Integration**.
4. Search for **Dahua RPC Control** and click **Download**.
5. **Restart** Home Assistant.

### Option 2: Manual Installation

1. Download the repository and copy the `custom_components/dahua_rpc_control` folder into your Home Assistant `config/custom_components` directory.
2. **Restart** Home Assistant.

---

## ⚙️ Configuration

### Manual Setup

1. Navigate to **Settings** > **Devices & Services**.
2. Click **Add Integration** and search for **Dahua RPC Control**.
3. Enter your camera's **IP Address**, **Username**, and **Password**.

### Auto-Discovery (SSDP)

This integration automatically listens for Dahua/Lorex broadcast signals on your network. If a new camera is found, it will appear as a discovered device in your integrations dashboard.

---

## 🎮 Entities Created

| Platform | Entity Name | Description |
| --- | --- | --- |
| **Camera** | `Camera Stream` | High-quality RTSP stream for live viewing. |
| **Switch** | `Camera White Light` | Toggles the onboard white LED via CoaxialControlIO. |
| **Switch** | `Basic Motion Detection` | Enables or disables the core motion sensor. |
| **Select** | `Active Scene Profile` | Switch between Auto, Day, Night, or Normal profiles. |
| **Select** | `Illumination Mode` | Choose between InfraredMode, WhiteMode, or AIMode. |
| **Number** | `Siren Volume` | Adjust the siren speaker volume (0-100%). |
| **Button** | `Reboot Camera` | Performs a soft system reboot of the hardware. |

---

## 🤖 Sample Automations

### 1. The "Intruder Alert" Siren Override

This automation uses the "Activate Siren (Continuous)" logic to fire a 10-minute siren if the alarm is triggered, ensuring the intruder is met with sustained noise regardless of the camera's default 10-second timer.

```yaml
automation:
  alias: "Security: Intruder Siren Alert"
  trigger:
    - platform: state
      entity_id: alarm_control_panel.home_alarm
      to: "triggered"
  action:
    - service: button.press
      target:
        entity_id: button.dahua_camera_activate_siren_continuous

```

### 2. Intelligent Night Vision Switching

Force the camera into "White Light" mode only when a person is detected, otherwise keeping it in stealthy "Infrared" mode.

```yaml
automation:
  alias: "Lighting: Person Detected Night Mode"
  trigger:
    - platform: state
      entity_id: binary_sensor.camera_person_occupancy
      to: "on"
  action:
    - service: select.select_option
      target:
        entity_id: select.dahua_camera_illumination_mode
      data:
        option: "WhiteMode"

```

---

## 📝 Custom Services

### `dahua_rpc_control.set_video_analyse_type`

Sets the global Video Analyse Scene Type. This is useful for advanced AI configurations where you need to toggle "Normal" analysis logic via script.

**Example Call:**

```yaml
service: dahua_rpc_control.set_video_analyse_type
data:
  type: "Normal"

```

---

## ⚠️ Disclaimer

*This project is not affiliated with, authorized, or endorsed by Dahua Technology. Use at your own risk*.
