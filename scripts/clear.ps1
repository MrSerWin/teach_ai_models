<#
.SYNOPSIS
    Освобождает место на диске: удаляет в Корзину папки node_modules
    и билд-мусор C#/Xamarin/.NET проектов (bin, obj, .vs, packages).

.DESCRIPTION
    Скрипт рекурсивно обходит диск и ищет:
      1. Папки node_modules (не заходя внутрь уже найденных).
      2. Временные/билд-папки .NET и Xamarin: bin, obj, .vs, packages.
         Чтобы не удалить постороннюю папку с именем bin/obj/packages,
         такие папки удаляются ТОЛЬКО если рядом (в той же родительской
         папке) есть проектный файл: *.sln, *.csproj, *.fsproj, *.vbproj,
         *.shproj, project.json. Папка .vs удаляется рядом с *.sln.
      Найденное перемещается в Корзину Windows.

.PARAMETER Path
    Диск или папка для сканирования. По умолчанию C:\

.PARAMETER SkipNodeModules
    Не трогать node_modules (только .NET/Xamarin мусор).

.PARAMETER SkipDotNet
    Не трогать bin/obj/.vs/packages (только node_modules).

.PARAMETER WhatIf
    Только показать, что будет удалено, без фактического удаления.

.EXAMPLE
    .\clear.ps1
    .\clear.ps1 -Path D:\
    .\clear.ps1 -Path C:\ -WhatIf
    .\clear.ps1 -Path D:\Projects -SkipNodeModules
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Path = 'C:\',
    [switch]$SkipNodeModules,
    [switch]$SkipDotNet
)

# Нужно для удаления в Корзину
Add-Type -AssemblyName Microsoft.VisualBasic

# Проверка, что путь существует (частая ошибка — опечатка/кириллица в букве диска)
if (-not (Test-Path -LiteralPath $Path)) {
    Write-Host "ОШИБКА: путь '$Path' не существует." -ForegroundColor Red
    Write-Host "Проверь букву диска (возможно, в ней кириллический символ) и слэш, например: G:\" -ForegroundColor Yellow
    return
}

# Имена билд-папок .NET / Xamarin
$dotNetDirs = @('bin', 'obj', 'packages', '.vs')
# Маски проектных файлов — признак того, что bin/obj можно удалять
$projectFileMasks = @('*.sln', '*.csproj', '*.fsproj', '*.vbproj', '*.shproj', 'project.json')

Write-Host "Сканирование '$Path'..." -ForegroundColor Cyan
Write-Host "(это может занять несколько минут)" -ForegroundColor DarkGray

$found = New-Object System.Collections.Generic.List[string]
$totalBytes = 0

# Есть ли в папке хотя бы один проектный файл .NET/Xamarin?
function Test-IsProjectDir {
    param([string]$Dir)
    foreach ($mask in $projectFileMasks) {
        try {
            $hit = [System.IO.Directory]::EnumerateFiles($Dir, $mask).GetEnumerator()
            if ($hit.MoveNext()) { return $true }
        } catch { }
    }
    return $false
}

# Рекурсивный обход. При нахождении целевой папки не углубляемся внутрь неё.
function Find-Targets {
    param([string]$Dir)

    $subDirs = $null
    try {
        $subDirs = [System.IO.Directory]::GetDirectories($Dir)
    } catch {
        return  # нет доступа / системная папка — пропускаем
    }

    # Является ли текущая папка .NET-проектом (рядом есть .csproj/.sln/...)?
    $parentIsProject = $false
    if (-not $SkipDotNet) {
        $parentIsProject = Test-IsProjectDir -Dir $Dir
    }

    foreach ($d in $subDirs) {
        $leaf = Split-Path $d -Leaf

        if (-not $SkipNodeModules -and $leaf -ieq 'node_modules') {
            $found.Add($d)
            continue
        }

        if (-not $SkipDotNet -and ($dotNetDirs -icontains $leaf)) {
            # bin/obj/packages/.vs удаляем только если родитель — проектная папка
            if ($parentIsProject) {
                $found.Add($d)
                continue
            }
        }

        Find-Targets -Dir $d
    }
}

Find-Targets -Dir $Path

if ($found.Count -eq 0) {
    Write-Host "Папки для очистки не найдены." -ForegroundColor Green
    return
}

Write-Host ""
Write-Host "Найдено папок для удаления: $($found.Count)" -ForegroundColor Yellow
Write-Host ""

foreach ($dir in $found) {
    $size = 0
    try {
        $size = (Get-ChildItem -LiteralPath $dir -Recurse -Force -File -ErrorAction SilentlyContinue |
                 Measure-Object -Property Length -Sum).Sum
        if (-not $size) { $size = 0 }
    } catch { $size = 0 }
    $totalBytes += $size

    $sizeMb = [math]::Round($size / 1MB, 1)

    if ($PSCmdlet.ShouldProcess($dir, "Удалить в Корзину ($sizeMb MB)")) {
        try {
            [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(
                $dir,
                [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,
                [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin
            )
            Write-Host "  Удалено: $dir  ($sizeMb MB)" -ForegroundColor Green
        } catch {
            Write-Host "  ОШИБКА:  $dir  -> $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "  [WhatIf] $dir  ($sizeMb MB)" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host ("Итого: $($found.Count) папок, ~{0} GB" -f [math]::Round($totalBytes / 1GB, 2)) -ForegroundColor Cyan
Write-Host "Удалённые папки находятся в Корзине." -ForegroundColor Cyan
