# Flash the Praetor ISO to a USB disk and add a CIDATA partition (Windows).
# RUN IN AN ELEVATED POWERSHELL. This erases the target disk.
#
#   .\tools\flash-praetor.ps1 -DiskNumber 1 -Iso .\iso\out\praetor-2026.09.10.iso `
#       -Private C:\path\to\praetor-private -Log .\iso\flash.log
#
# Find the disk number with: Get-Disk | Format-Table Number,FriendlyName,BusType,Size
param(
  [Parameter(Mandatory)][int]$DiskNumber,
  [Parameter(Mandatory)][string]$Iso,
  [string]$Private = "",
  [string]$Log = "$PSScriptRoot\..\iso\flash.log",
  # Windows' volume manager often refuses to create volumes on an isohybrid disk, so the
  # CIDATA step may fail on some machines. Use -NoCidata with a *-personal.iso (private
  # layer baked in) or put praetor-private on a separate CIDATA-labelled stick.
  [switch]$NoCidata
)
$ErrorActionPreference = 'Stop'
# .NET file APIs resolve relative paths against the process cwd (System32 when elevated),
# so make every path absolute against the caller's location first.
$Iso = (Resolve-Path -LiteralPath $Iso).Path
if ($Private) { $Private = (Resolve-Path -LiteralPath $Private).Path }
$Log = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Log))
Start-Transcript -Path $Log -Force | Out-Null
try {
  $disk = Get-Disk -Number $DiskNumber
  if ($disk.BusType -ne 'USB') { throw "Disk $DiskNumber is not USB ($($disk.BusType)); refusing." }
  if ($disk.IsBoot -or $disk.IsSystem) { throw "Disk $DiskNumber is a boot/system disk; refusing." }
  Write-Output "Target: disk $DiskNumber $($disk.FriendlyName) $([math]::Round($disk.Size/1GB,1)) GB"
  Write-Output "ISO: $Iso ($([math]::Round((Get-Item $Iso).Length/1MB)) MB)"

  # 1. Detach volumes and wipe the partition table.
  Get-Partition -DiskNumber $DiskNumber -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.DriveLetter) {
      Remove-PartitionAccessPath -DiskNumber $DiskNumber -PartitionNumber $_.PartitionNumber `
        -AccessPath "$($_.DriveLetter):" -ErrorAction SilentlyContinue
    }
  }
  Clear-Disk -Number $DiskNumber -RemoveData -RemoveOEM -Confirm:$false -ErrorAction SilentlyContinue
  # Removable media cannot be set offline; clearing the partitions is enough to release the volume.
  Start-Sleep 3

  # 2. Raw-write the ISO. archiso images are hybrid, so this alone makes the stick bootable.
  $in  = [System.IO.File]::OpenRead($Iso)
  $out = New-Object System.IO.FileStream("\\.\PhysicalDrive$DiskNumber",
           [System.IO.FileMode]::Open, [System.IO.FileAccess]::Write,
           [System.IO.FileShare]::None, 1MB, [System.IO.FileOptions]::WriteThrough)
  # Write the first 1 MB (MBR + partition table) LAST. If it goes first, Windows re-reads
  # the partition table mid-write, mounts any volume whose data already exists on the stick
  # (e.g. the EFI partition from a previous flash), and then denies writes to that range.
  $head = 1MB
  $headBuf = New-Object byte[] $head
  $headLen = $in.Read($headBuf, 0, $head)
  $buf = New-Object byte[] (4MB); $total = $headLen; $len = $in.Length; $next = 256MB
  $out.Seek($head, [System.IO.SeekOrigin]::Begin) | Out-Null
  while (($n = $in.Read($buf, 0, $buf.Length)) -gt 0) {
    $out.Write($buf, 0, $n); $total += $n
    if ($total -ge $next) { Write-Output ("  written {0:N0} / {1:N0} MB" -f ($total/1MB), ($len/1MB)); $next += 256MB }
  }
  $out.Flush()
  $out.Seek(0, [System.IO.SeekOrigin]::Begin) | Out-Null
  $out.Write($headBuf, 0, $headLen)
  $out.Flush(); $out.Dispose(); $in.Dispose()
  Write-Output "Raw write complete: $total bytes (MBR written last)"
  if ($NoCidata) { Write-Output "Skipping CIDATA partition (-NoCidata)."; Write-Output "FLASH_OK"; return }

  # 3. Bring the disk back and add a CIDATA partition in the free space.
  Set-Disk -Number $DiskNumber -IsReadOnly $false -ErrorAction SilentlyContinue
  Update-Disk -Number $DiskNumber -ErrorAction SilentlyContinue
  Start-Sleep 3
  Get-Partition -DiskNumber $DiskNumber | Format-Table PartitionNumber,Size,Type -AutoSize | Out-String | Write-Output
  $p = New-Partition -DiskNumber $DiskNumber -UseMaximumSize
  # The new volume can take a few seconds to appear after a raw write; retry the format.
  $formatted = $false
  for ($i = 0; $i -lt 10 -and -not $formatted; $i++) {
    Start-Sleep 3
    try {
      $p = Get-Partition -DiskNumber $DiskNumber -PartitionNumber $p.PartitionNumber
      Format-Volume -Partition $p -FileSystem FAT32 -NewFileSystemLabel CIDATA -Confirm:$false | Out-Null
      $formatted = $true
    } catch { Write-Output "  waiting for the new volume ($($i+1)/10)..." }
  }
  if (-not $formatted) { throw "Could not format the CIDATA partition; format partition $($p.PartitionNumber) on disk $DiskNumber by hand." }
  $p | Add-PartitionAccessPath -AssignDriveLetter -ErrorAction SilentlyContinue
  Start-Sleep 2
  $letter = (Get-Partition -DiskNumber $DiskNumber -PartitionNumber $p.PartitionNumber).DriveLetter
  if (-not $letter) { throw "CIDATA partition has no drive letter; assign one in Disk Management and copy praetor-private by hand." }
  Write-Output "CIDATA partition: $($letter): $([math]::Round($p.Size/1GB,1)) GB"

  # 4. Copy the private layer, if given.
  if ($Private) {
    $dest = "$($letter):\praetor-private"
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    robocopy $Private $dest /E /XD .git /XF .gitignore /NFL /NDL /NJH /NJS | Out-Null
    Write-Output "Copied private layer to $dest"
    Get-ChildItem -Recurse $dest | Select-Object FullName | Out-String | Write-Output
  }
  Write-Output "FLASH_OK"
} catch {
  Write-Output "FLASH_FAILED: $($_.Exception.Message)"
  Write-Output $_.ScriptStackTrace
} finally {
  Stop-Transcript | Out-Null
}
