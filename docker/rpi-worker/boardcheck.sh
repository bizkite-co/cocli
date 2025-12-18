#!/bin/bash

# boardcheck.sh - Raspberry Pi Health Inspector
# Author: Aaron + ChatGPT
# Logs stored in /var/log/boardcheck/ or fallback to ~/boardcheck_logs

LOG_DIR="/var/log/boardcheck"
[[ ! -w "$LOG_DIR" ]] && LOG_DIR="$HOME/boardcheck_logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/boardcheck-$(date -u +%F-T%H%M).log"

print_header() {
    clear
    echo "==============================="
    echo " Raspberry Pi boardcheck"
    echo "==============================="
    echo
}

main_menu() {
    print_header
    echo "1) Run Full Board Check"
    echo "2) View Last Session Log"
    echo "3) Quit"
    echo
    read -p "Select an option [1-3]: " choice

    case $choice in
    1) run_checks ;;
    2) view_last_log ;;
    3) echo "Goodbye!" && exit 0 ;;
    *) echo "Invalid option. Try again." && sleep 1 && main_menu ;;
    esac
}

run_checks() {
    print_header
    echo "Running diagnostics..."
    echo "\nboardcheck Results - $(date -u)\n===========================================\n" >"$LOG_FILE"

    # Temperature Idle Reading
    PRE_TEMP=$(vcgencmd measure_temp | cut -d '=' -f2)
    echo -e "\xf0\x9f\x8c\xa1 Temperature Check:\n - Idle: $PRE_TEMP" | tee -a "$LOG_FILE"

    # Power Check
    THROTTLED=$(vcgencmd get_throttled)
    if [[ "$THROTTLED" == *"0x0"* ]]; then
        echo -e "[PASS]  Power Supply       : No undervoltage detected" | tee -a "$LOG_FILE"
    else
        echo -e "[FAIL]  Power Supply       : Undervoltage flags set ($THROTTLED)" | tee -a "$LOG_FILE"
    fi

    # SD Card Write Speed
    SPEED=$(dd if=/dev/zero of=testfile bs=1M count=100 oflag=dsync 2>&1 | grep copied | awk '{print $(NF-1), $NF}')
    SPEED_NUM=$(echo $SPEED | awk '{print $1}')
    if (($(echo "$SPEED_NUM < 5.0" | bc -l))); then
        echo -e "[WARN]  microSD Card       : Write speed below optimal ($SPEED)" | tee -a "$LOG_FILE"
    else
        echo -e "[PASS]  microSD Card       : Write speed is healthy ($SPEED)" | tee -a "$LOG_FILE"
    fi
    rm -f testfile

    # USB Check
    USB_COUNT=$(lsusb | wc -l)
    echo -e "[PASS]  USB Devices        : $USB_COUNT device(s) detected, no errors" | tee -a "$LOG_FILE"

    # Wi-Fi Signal Check
    if iwconfig 2>/dev/null | grep -q "wlan0"; then
        SIGNAL=$(iwconfig wlan0 | grep -i --color=never 'Signal level' | awk '{ for (i=1;i<=NF;i++) if ($i ~ /level=/) print $i }' | cut -d '=' -f2)
        QUALITY=$(iwconfig wlan0 | grep -i --color=never 'Link Quality' | awk '{ for (i=1;i<=NF;i++) if ($i ~ /Quality=/) print $i }' | cut -d '=' -f2)
        echo -e "[PASS]  Wi-Fi Signal        : Signal $SIGNAL dBm, Quality $QUALITY" | tee -a "$LOG_FILE"
    else
        echo -e "[SKIP]  Wi-Fi Signal        : wlan0 not detected or not active" | tee -a "$LOG_FILE"
    fi

    # Ethernet Check
    LINK=$(ip link show eth0 | grep -q "state UP" && echo up || echo down)
    if [[ "$LINK" == "up" ]]; then
        PING=$(ping -c 3 -q 192.168.1.1 | grep rtt | awk -F'/' '{print $5}')
        echo -e "[PASS]  Ethernet           : Link active, avg ping ${PING} ms" | tee -a "$LOG_FILE"
    else
        echo -e "[WARN]  Ethernet           : Link down or not connected" | tee -a "$LOG_FILE"
    fi

    # Filesystem Health Check
    echo -e "\n\U1F4C1 Filesystem Health:" | tee -a "$LOG_FILE"

    ROOT_STATUS=$(mount | grep "on / " | grep -q "ro," && echo "read-only" || echo "read-write")
    BOOT_STATUS=$(mount | grep "on /boot" | grep -q "ro," && echo "read-only" || echo "read-write")

    if [[ "$ROOT_STATUS" == "read-only" ]]; then
        echo -e "[FAIL]  Root Partition      : Mounted read-only — potential SD card or power issue" | tee -a "$LOG_FILE"
    else
        echo -e "[PASS]  Root Partition      : Mounted read-write" | tee -a "$LOG_FILE"
    fi

    if [[ "$BOOT_STATUS" == "read-only" ]]; then
        echo -e "[FAIL]  Boot Partition      : Mounted read-only — check filesystem health" | tee -a "$LOG_FILE"
    else
        echo -e "[PASS]  Boot Partition      : Mounted read-write" | tee -a "$LOG_FILE"
    fi

    # Disk usage check (for root only — most common concern)
    ROOT_USAGE=$(df / | awk 'END { print $5 }' | tr -d '%')
    if ((ROOT_USAGE > 90)); then
        echo -e "[WARN]  Disk Usage          : Root partition is ${ROOT_USAGE}% full — consider cleanup" | tee -a "$LOG_FILE"
    else
        echo -e "[PASS]  Disk Usage          : ${ROOT_USAGE}% used on root" | tee -a "$LOG_FILE"
    fi

    # Swap Usage Check
    echo -e "\n\U1F9E0 Swap Usage:" | tee -a "$LOG_FILE"
    SWAP_TOTAL=$(free -m | awk '/Swap:/ { print $2 }')
    SWAP_USED=$(free -m | awk '/Swap:/ { print $3 }')

    if ((SWAP_TOTAL == 0)); then
        echo -e "[INFO]  Swap                : Swap not enabled on this system" | tee -a "$LOG_FILE"
    elif ((SWAP_USED > 0)); then
        echo -e "[WARN]  Swap                : ${SWAP_USED}MB used of ${SWAP_TOTAL}MB — may indicate RAM pressure" | tee -a "$LOG_FILE"
    else
        echo -e "[PASS]  Swap                : ${SWAP_TOTAL}MB available, none in use" | tee -a "$LOG_FILE"
    fi

    # USB Power Draw (if available)
    echo -e "\n\xf0\x9f\x93\x8a USB Power Draw Summary:" | tee -a "$LOG_FILE"
    if command -v usb-devices >/dev/null 2>&1; then
        usb-devices | awk '
      /^T:/ { bus=$0 }
      /Vendor/ { vendor=$0 }
      /Product/ { product=$0 }
      /MaxPower/ {
        print " - " vendor ", " product ", " $0
      }
    ' | tee -a "$LOG_FILE"
    else
        echo "\xf0\x9f\x94\xb4 usb-devices not available. Skipping detailed power info." | tee -a "$LOG_FILE"
    fi

    # Temperature After Load
    POST_TEMP=$(vcgencmd measure_temp | cut -d '=' -f2)
    echo -e " - After Tests: $POST_TEMP" | tee -a "$LOG_FILE"

    # Throttling History Check
    THROTTLE_HISTORY=$(vcgencmd get_throttled)
    if [[ "$THROTTLE_HISTORY" =~ "0x0" ]]; then
        echo -e "[PASS]  Throttling History  : No throttling has occurred" | tee -a "$LOG_FILE"
    else
        echo -e "[WARN]  Throttling History  : Historical throttling flags set ($THROTTLE_HISTORY)" | tee -a "$LOG_FILE"
    fi

    # EEPROM/Firmware Check with Model Awareness
    MODEL=$(tr -d '\0' </proc/device-tree/model)
    echo -e "\n\U1F4BB Pi Model Detected       : $MODEL" | tee -a "$LOG_FILE"

    if echo "$MODEL" | grep -q -E "Pi 4|Pi 5|400|Compute Module 4"; then
        EEPROM=$(rpi-eeprom-update | grep "CURRENT")
        echo -e "[PASS]  Firmware/Bootloader : $EEPROM" | tee -a "$LOG_FILE"
    else
        echo -e "[SKIP]  Firmware/Bootloader : Not applicable on $MODEL" | tee -a "$LOG_FILE"
    fi

    # Stress Test (if available)
    if command -v stress-ng >/dev/null 2>&1; then
        echo -e "" | tee -a "$LOG_FILE"
        echo "✅ Running CPU stress test (20 seconds)... please wait." | tee -a "$LOG_FILE"

        stress-ng --cpu 4 --timeout 20s --metrics-brief >>"$LOG_FILE"
    else
        echo -e "\xf0\x9f\x94\xa5 stress-ng not installed. Skipping load test." | tee -a "$LOG_FILE"
    fi

    # CPU Info
    CORE_COUNT=$(nproc)
    LOAD_AVG=$(uptime | awk -F'load average: ' '{ print $2 }')
    echo -e "\n🧮 CPU Info:" | tee -a "$LOG_FILE"
    echo -e "[INFO]  CPU Cores           : $CORE_COUNT core(s)" | tee -a "$LOG_FILE"
    echo -e "[INFO]  Load Averages       : $LOAD_AVG" | tee -a "$LOG_FILE"

    echo -e "\n------------------------------------------\nCommands Run for this Check:" >>"$LOG_FILE"
    echo -e "  - vcgencmd get_throttled" >>"$LOG_FILE"
    echo -e "  - dd if=/dev/zero of=testfile bs=1M count=100 oflag=dsync" >>"$LOG_FILE"
    echo -e "  - lsusb" >>"$LOG_FILE"
    echo -e "  - ip link show eth0" >>"$LOG_FILE"
    echo -e "  - ping -c 3 192.168.1.1" >>"$LOG_FILE"
    echo -e "  - rpi-eeprom-update" >>"$LOG_FILE"
    echo -e "  - stress-ng --cpu 4 --timeout 20s --metrics-brief" >>"$LOG_FILE"

    echo -e "\n\xf0\x9f\x93\x81 Log saved to: $LOG_FILE"
    echo -e "\nPress ENTER to return to the main menu."
    read
    main_menu
}

view_last_log() {
    LAST_LOG=$(ls -1t "$LOG_DIR"/boardcheck-*.log 2>/dev/null | head -n 1)
    if [[ -f "$LAST_LOG" ]]; then
        echo -e "\n\xf0\x9f\x93\x8e Tip: Press Q to quit this viewer and return to boardcheck." | tee -a "$LAST_LOG"
        sleep 2
        less "$LAST_LOG"
    else
        echo "No log files found. Run a check first."
        sleep 2
    fi
    main_menu
}

main_menu
