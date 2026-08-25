param(
    [Parameter(Mandatory = $true)][string]$InputPath,
    [Parameter(Mandatory = $true)][string]$OutputPdf,
    [ValidateSet('auto','word','excel','powerpoint')][string]$Application = 'auto',
    [string]$ThumbnailDirectory,
    [string]$HighResolutionSlides = ''
)

$ErrorActionPreference = 'Stop'

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
public static class OfficeWindowControl {
    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}

public sealed class PowerPointWindowGuard : IDisposable {
    private readonly HashSet<int> baselineProcessIds = new HashSet<int>();
    private volatile bool running;
    private Thread worker;

    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    private static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

    public PowerPointWindowGuard() {
        foreach (Process process in Process.GetProcessesByName("POWERPNT")) {
            try { baselineProcessIds.Add(process.Id); }
            finally { process.Dispose(); }
        }
    }

    public void Start() {
        if (running) return;
        running = true;
        worker = new Thread(HideNewPowerPointWindows);
        worker.IsBackground = true;
        worker.Name = "PowerPointWindowGuard";
        worker.Start();
    }

    private void HideNewPowerPointWindows() {
        while (running) {
            foreach (Process process in Process.GetProcessesByName("POWERPNT")) {
                try {
                    if (!baselineProcessIds.Contains(process.Id)) HideWindowsForProcess(process.Id);
                }
                finally { process.Dispose(); }
            }
            Thread.Sleep(10);
        }
    }

    private static void HideWindowsForProcess(int targetProcessId) {
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            uint processId;
            GetWindowThreadProcessId(hWnd, out processId);
            if (processId == (uint)targetProcessId) ShowWindowAsync(hWnd, 0);
            return true;
        }, IntPtr.Zero);
    }

    public void Stop() {
        running = false;
        if (worker != null && worker.IsAlive) worker.Join(1000);
    }

    public void Dispose() { Stop(); }
}
'@

function Hide-PowerPointWindow {
    param($PowerPointApplication)
    try {
        $handle = [IntPtr][int64]$PowerPointApplication.HWND
        if ($handle -ne [IntPtr]::Zero) {
            # 0 = SW_HIDE
            [void][OfficeWindowControl]::ShowWindowAsync($handle, 0)
        }
    }
    catch {
        # WithWindow=false remains the primary control if HWND is unavailable.
    }
}

$inputFull = [IO.Path]::GetFullPath($InputPath)
$outputFull = [IO.Path]::GetFullPath($OutputPdf)
if (-not (Test-Path -LiteralPath $inputFull -PathType Leaf)) { throw "Input not found: $inputFull" }
if ([IO.Path]::GetExtension($outputFull).ToLowerInvariant() -ne '.pdf') { throw 'OutputPdf must end in .pdf' }
[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputFull)) | Out-Null

if ($Application -eq 'auto') {
    $ext = [IO.Path]::GetExtension($inputFull).ToLowerInvariant()
    if ($ext -in '.doc','.docx','.docm') { $Application = 'word' }
    elseif ($ext -in '.xls','.xlsx','.xlsm') { $Application = 'excel' }
    elseif ($ext -in '.ppt','.pptx','.pptm') { $Application = 'powerpoint' }
    else { throw "Unsupported Office extension: $ext" }
}

$app = $document = $workbook = $presentation = $windowGuard = $null
$lowResolutionCount = 0
$highResolutionCount = 0
$presentationOpens = 0
$powerpointStarts = 0
try {
    if ($Application -eq 'word') {
        $app = New-Object -ComObject Word.Application
        $app.Visible = $false
        $app.DisplayAlerts = 0
        $document = $app.Documents.Open($inputFull, $false, $true)
        $document.ExportAsFixedFormat($outputFull, 17)
    }
    elseif ($Application -eq 'excel') {
        $app = New-Object -ComObject Excel.Application
        $app.Visible = $false
        $app.DisplayAlerts = $false
        $workbook = $app.Workbooks.Open($inputFull, 0, $true)
        $workbook.ExportAsFixedFormat(0, $outputFull)
    }
    else {
        $windowGuard = New-Object PowerPointWindowGuard
        $windowGuard.Start()
        $app = New-Object -ComObject PowerPoint.Application
        # 1 = ppAlertsNone.
        $app.DisplayAlerts = 1
        Hide-PowerPointWindow $app
        $powerpointStarts = 1
        # ReadOnly=true, Untitled=false, WithWindow=false.
        $presentation = $app.Presentations.Open($inputFull, -1, 0, 0)
        Hide-PowerPointWindow $app
        $presentationOpens = 1
        # 32 = ppSaveAsPDF.
        Hide-PowerPointWindow $app
        $presentation.SaveAs($outputFull, 32)

        if (-not [string]::IsNullOrWhiteSpace($ThumbnailDirectory)) {
            $thumbnailFull = [IO.Path]::GetFullPath($ThumbnailDirectory)
            [IO.Directory]::CreateDirectory($thumbnailFull) | Out-Null
            $highDirectory = Join-Path $thumbnailFull 'high'
            $highSet = @{}
            foreach ($value in ($HighResolutionSlides -split ',')) {
                $trimmed = $value.Trim()
                if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
                    $index = 0
                    if (-not [int]::TryParse($trimmed, [ref]$index) -or $index -lt 1) {
                        throw "Invalid HighResolutionSlides value: $trimmed"
                    }
                    $highSet[$index] = $true
                }
            }
            if ($highSet.Count -gt 0) {
                [IO.Directory]::CreateDirectory($highDirectory) | Out-Null
            }
            $lowWidth = 640
            $lowHeight = [int][Math]::Round(
                $lowWidth * [double]$presentation.PageSetup.SlideHeight /
                [double]$presentation.PageSetup.SlideWidth
            )
            $highWidth = 1920
            $highHeight = [int][Math]::Round(
                $highWidth * [double]$presentation.PageSetup.SlideHeight /
                [double]$presentation.PageSetup.SlideWidth
            )
            for ($slideIndex = 1; $slideIndex -le $presentation.Slides.Count; $slideIndex++) {
                $slide = $presentation.Slides.Item($slideIndex)
                try {
                    $name = 'slide-{0:D3}.png' -f $slideIndex
                    $slide.Export((Join-Path $thumbnailFull $name), 'PNG', $lowWidth, $lowHeight)
                    $lowResolutionCount++
                    if ($highSet.ContainsKey($slideIndex)) {
                        $slide.Export((Join-Path $highDirectory $name), 'PNG', $highWidth, $highHeight)
                        $highResolutionCount++
                    }
                }
                finally {
                    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($slide)
                }
            }
        }
    }
}
finally {
    if ($document) { $document.Close($false) }
    if ($workbook) { $workbook.Close($false) }
    if ($presentation) { $presentation.Close() }
    if ($app) { $app.Quit() }
    foreach ($obj in @($document,$workbook,$presentation,$app)) {
        if ($obj) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($obj) }
    }
    if ($windowGuard) { $windowGuard.Stop() }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

if (-not (Test-Path -LiteralPath $outputFull -PathType Leaf)) { throw "Office did not create PDF: $outputFull" }
[ordered]@{
    application = $Application
    input = $inputFull
    pdf = $outputFull
    pdf_created = $true
    powerpoint_starts = $powerpointStarts
    presentation_opens = $presentationOpens
    low_resolution_slides = $lowResolutionCount
    high_resolution_slides = $highResolutionCount
} | ConvertTo-Json -Compress
