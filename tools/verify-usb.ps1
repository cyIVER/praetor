# Verify a flashed Praetor USB against its ISO. RUN ELEVATED (raw disk read).
#   .\tools\verify-usb.ps1 -DiskNumber 1 -Iso .\iso\out\praetor-....iso        # quick: MBR + EFI partition
#   .\tools\verify-usb.ps1 -DiskNumber 1 -Iso .\iso\out\praetor-....iso -Full  # every byte (slow on USB 2.0)
param(
  [Parameter(Mandatory)][int]$DiskNumber,
  [Parameter(Mandatory)][string]$Iso,
  [switch]$Full
)
$ErrorActionPreference = 'Stop'
$Iso = (Resolve-Path -LiteralPath $Iso).Path
$dev = New-Object System.IO.FileStream("\\.\PhysicalDrive$DiskNumber",
         [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite, 1MB)
$img = [System.IO.File]::OpenRead($Iso)
$sha = [System.Security.Cryptography.SHA256]::Create()

function Hash-Range($stream, [long]$offset, [long]$length) {
  $stream.Seek($offset, [System.IO.SeekOrigin]::Begin) | Out-Null
  $h = [System.Security.Cryptography.SHA256]::Create()
  $buf = New-Object byte[] (4MB); $left = $length
  while ($left -gt 0) {
    $n = $stream.Read($buf, 0, [int][math]::Min($buf.Length, $left))
    if ($n -le 0) { break }
    $h.TransformBlock($buf, 0, $n, $null, 0) | Out-Null; $left -= $n
  }
  $h.TransformFinalBlock($buf, 0, 0) | Out-Null
  return ([BitConverter]::ToString($h.Hash) -replace '-', '').ToLower()
}

$ranges = @(@{ name = 'MBR + first 1 MB'; off = 0; len = 1MB })
foreach ($p in Get-Partition -DiskNumber $DiskNumber -ErrorAction SilentlyContinue) {
  $ranges += @{ name = "partition $($p.PartitionNumber) ($([math]::Round($p.Size/1MB)) MB @ $($p.Offset))"; off = $p.Offset; len = $p.Size }
}
if ($Full) { $ranges += @{ name = 'entire image'; off = 0; len = $img.Length } }

$ok = $true
foreach ($r in $ranges) {
  $a = Hash-Range $img $r.off $r.len
  $b = Hash-Range $dev $r.off $r.len
  $status = if ($a -eq $b) { 'MATCH' } else { 'MISMATCH'; $ok = $false }
  Write-Output ("{0,-9} {1}" -f $status, $r.name)
}
$dev.Dispose(); $img.Dispose()
Write-Output $(if ($ok) { 'VERIFY_OK' } else { 'VERIFY_FAILED' })
