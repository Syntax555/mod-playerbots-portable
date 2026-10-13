# GitHub Actions error annotations for the Windows build job.
# Dot-source this file in a step: . ./scripts/WriteActionsError.ps1

# Writes one ::error annotation. A message longer than the 8,000 characters
# kept per annotation loses its end, or its start with -Tail so that the
# last lines of a log excerpt remain.
function Write-ActionsError {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Message,
        [switch]$Tail
    )
    $limit = 8000
    if ($Message.Length -gt $limit) {
        $Message = if ($Tail) { $Message.Substring($Message.Length - $limit) } else { $Message.Substring(0, $limit) }
    }
    $data = $Message.Replace('%', '%25').Replace("`r", '%0D').Replace("`n", '%0A')
    # Annotation properties also reserve ':' and ','.
    $property = $Title.Replace('%', '%25').Replace("`r", '%0D').Replace("`n", '%0A').Replace(':', '%3A').Replace(',', '%2C')
    Write-Output "::error title=$property::$data"
}

# Runs a step body and reports a terminating error as one annotation.
function Invoke-ActionsStep {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][scriptblock]$Body
    )
    try {
        & $Body
    } catch {
        Write-ActionsError -Title $Title -Message $_.Exception.Message
        exit 1
    }
}
