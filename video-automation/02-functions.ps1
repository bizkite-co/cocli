# 02-functions.ps1: Core profile functions (Directory/State changes only)

# Helper to reload profile components
function rpro {
    $configDir = "$HOME/.config/powershell/conf.d"
    if (Test-Path $configDir) {
        Get-ChildItem -Path $configDir -Filter *.ps1 | Sort-Object Name | ForEach-Object {
            . $_.FullName
        }
    }
}

# Touchpad toggle (Requires Admin/Hardware access)
function global:touchpad()
{
  PARAM([boolean]$enabled = $true)
  if($enabled){
    Enable-PnpDevice -InstanceId "HID\TARGET_KIP&CATEGORY_HID&COL02\4&7254205&0&0001" -Confirm:$false
  } else {
    Disable-PnpDevice -InstanceId "HID\TARGET_KIP&CATEGORY_HID&COL02\4&7254205&0&0001" -Confirm:$false
  }
}

function Normalize-Video {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Path
    )
    $scriptPath = "$HOME\.config\powershell\bin\Normalize-Video.py"
    python $scriptPath $Path
}