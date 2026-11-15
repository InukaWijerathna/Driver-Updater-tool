# An in-memory WUA substitute. New-Object rejects every real COM activation.
$config = '__CONFIG__' | ConvertFrom-Json
$script:downloadCalls = 0
$script:installedIDs = @()
$script:available = @()
foreach ($entry in $config.Updates) {
    $script:available += [pscustomobject]@{
        Identity = [pscustomobject]@{ UpdateID = $entry.ID; RevisionNumber = $entry.Revision }
        Title = 'Mock driver'; IsDownloaded = $false
        DownloadCode = $entry.DownloadCode; InstallCode = $entry.InstallCode
    }
}
function New-Object {
    param([string]$ComObject)
    if ($ComObject -eq 'Microsoft.Update.UpdateColl') {
        return ,([Collections.ArrayList]::new())
    }
    if ($ComObject -ne 'Microsoft.Update.Session') { throw 'Real COM access forbidden in tests' }
    $session = [pscustomobject]@{}
    $session | Add-Member ScriptMethod CreateUpdateSearcher {
        $searcher = [pscustomobject]@{}
        $searcher | Add-Member ScriptMethod Search {
            param($criteria)
            return [pscustomobject]@{ ResultCode = 2; Updates = $script:available }
        }
        return $searcher
    }
    $session | Add-Member ScriptMethod CreateUpdateDownloader {
        $downloader = [pscustomobject]@{ Updates = $null }
        $downloader | Add-Member ScriptMethod Download {
            $script:downloadCalls++
            $entries = @($this.Updates.ToArray())
            foreach ($entry in $entries) { $entry.IsDownloaded = $entry.DownloadCode -eq 2 }
            $code = if (@($entries | Where-Object DownloadCode -ne 2).Count) { 3 } else { 2 }
            $result = [pscustomobject]@{ ResultCode = $code; Entries = $entries }
            $result | Add-Member ScriptMethod GetUpdateResult {
                param($index)
                return [pscustomobject]@{ ResultCode = $this.Entries[$index].DownloadCode; HResult = 0 }
            }
            return $result
        }
        return $downloader
    }
    $session | Add-Member ScriptMethod CreateUpdateInstaller {
        $installer = [pscustomobject]@{ Updates = $null }
        $installer | Add-Member ScriptMethod Install {
            if ($config.ThrowOnInstall) { throw 'Simulated installation exception' }
            $entries = @($this.Updates.ToArray())
            foreach ($entry in $entries) { $script:installedIDs += $entry.Identity.UpdateID }
            $code = if (@($entries | Where-Object InstallCode -ne 2).Count) { 3 } else { 2 }
            $result = [pscustomobject]@{ ResultCode = $code; RebootRequired = $true; Entries = $entries }
            $result | Add-Member ScriptMethod GetUpdateResult {
                param($index)
                return [pscustomobject]@{
                    ResultCode = $this.Entries[$index].InstallCode; HResult = 0; RebootRequired = $true
                }
            }
            return $result
        }
        return $installer
    }
    return $session
}
