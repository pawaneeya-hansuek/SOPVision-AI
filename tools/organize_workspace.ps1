param([switch]$Apply)
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$prefix=$projectRoot+[IO.Path]::DirectorySeparatorChar
$protected=@()
$ready=Join-Path $projectRoot '.test-supervisor-ready.json'
if(Test-Path -LiteralPath $ready){
    try{$info=Get-Content -LiteralPath $ready -Raw | ConvertFrom-Json;$protected+=Split-Path -Parent $info.portrait}catch{}
}
$testing=@(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(python|pythonw|node)(\.exe)?$' -and
    $_.CommandLine -match '(serve_supervisor_ui|smoke_camera_network|pytest|tests[/\\].*\.cjs)'
})
$plan=@()
foreach($item in Get-ChildItem -LiteralPath $projectRoot -Force){
    if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){continue}
    $category=$null
    if($item.PSIsContainer -and $item.Name -like '.test-output-*' -and !$testing.Count -and $item.FullName -notin $protected){$category='artifacts/test-runs/archived'}
    elseif(!$item.PSIsContainer -and $item.Name -like '*preview*.png'){$category='output/previews'}
    elseif(!$item.PSIsContainer -and $item.Name -like 'sopvision.pre-*.bak'){$category='backups/legacy'}
    elseif(!$item.PSIsContainer -and $item.Name -in @('STABILITY.md','SUPERVISOR.md','INSPECTION_FIX.md')){$category='docs'}
    if(!$category){continue}
    $source=[IO.Path]::GetFullPath($item.FullName)
    $destination=[IO.Path]::GetFullPath((Join-Path (Join-Path $projectRoot $category) $item.Name))
    if(!$source.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) -or !$destination.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Path outside project; nothing moved'}
    if(Test-Path -LiteralPath $destination){throw "Destination already exists: $destination"}
    $plan+= [pscustomobject]@{Source=$source;Destination=$destination;Category=$category}
}
$plan | Group-Object Category | Select-Object Name,Count | Format-Table -AutoSize
if(!$Apply){Write-Output 'Preview only. Use -Apply to move these items without deletion.';return}
$manifest=Join-Path $projectRoot ('artifacts/organization-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.json')
New-Item -ItemType Directory -Path (Split-Path -Parent $manifest) -Force | Out-Null
$completed=@()
foreach($entry in $plan){
    $parent=Split-Path -Parent $entry.Destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $checkedParent=(Resolve-Path -LiteralPath $parent).Path
    if(!$checkedParent.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase)){throw 'Destination escaped project'}
    Move-Item -LiteralPath $entry.Source -Destination $entry.Destination
    $completed+=$entry
    ConvertTo-Json -InputObject $completed -Depth 3 | Set-Content -LiteralPath $manifest -Encoding utf8
}
Write-Output ("Moved "+$completed.Count+" items. Manifest: "+$manifest)
