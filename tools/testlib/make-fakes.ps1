# Apex5 Unleashed multi-config test lib: build fake "game" exes + a fake Mod (ASCII only on purpose).
# Usage:  powershell -ExecutionPolicy Bypass -File make-fakes.ps1          (build + open folder)
#         powershell -ExecutionPolicy Bypass -File make-fakes.ps1 -Clean   (delete the folder)
param([switch]$Clean)
$ErrorActionPreference = 'Stop'
$out = Join-Path $env:TEMP 'apex5-testlib'
if ($Clean) { Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue; Write-Host "removed $out"; exit 0 }

$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { throw "csc.exe not found: $csc" }
New-Item -ItemType Directory -Force $out | Out-Null

$gameSrc = @'
using System; using System.Drawing; using System.Windows.Forms;
static class P {
  [STAThread] static void Main() {
    string n = System.IO.Path.GetFileName(Application.ExecutablePath);
    Form f = new Form(); f.Text = "FAKE GAME - " + n; f.Width = 520; f.Height = 200;
    f.StartPosition = FormStartPosition.CenterScreen;
    Label l = new Label(); l.Dock = DockStyle.Fill; l.TextAlign = ContentAlignment.MiddleCenter;
    l.Font = new Font("Segoe UI", 12);
    l.Text = "Fake game process: " + n + "\nKeep this window in the foreground.";
    f.Controls.Add(l); Application.Run(f);
  }
}
'@
$modSrc = @'
static class M { static void Main(string[] a) { System.Threading.Thread.Sleep(-1); } }
'@
$gameCs = Join-Path $out '_game.cs'; $modCs = Join-Path $out '_mod.cs'
Set-Content -Path $gameCs -Value $gameSrc -Encoding ASCII
Set-Content -Path $modCs -Value $modSrc -Encoding ASCII

$base = Join-Path $out '_game.exe'
& $csc /nologo /target:winexe "/out:$base" /r:System.Windows.Forms.dll /r:System.Drawing.dll $gameCs
if ($LASTEXITCODE -ne 0) { throw "compile game failed" }
& $csc /nologo /target:winexe "/out:$(Join-Path $out 'FakeMod.exe')" $modCs
if ($LASTEXITCODE -ne 0) { throw "compile mod failed" }

# fake game names must match the exe lists in the json sources / the built-in card
foreach ($n in 'gowr.exe', 'apex5_arena.exe', 'apex5_modgame.exe', 'apex5_modonly.exe') {
    Copy-Item $base (Join-Path $out $n) -Force
}
Remove-Item $base, $gameCs, $modCs -Force
Write-Host "built in $out :"
Get-ChildItem $out | ForEach-Object { Write-Host "  $($_.Name)" }
Start-Process explorer.exe $out
