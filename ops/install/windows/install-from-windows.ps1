<#
    Install Company Brain on your server, from a Windows computer.

    Double-click install-from-windows.cmd, which sits beside this file. Or right-click this
    file and choose Run with PowerShell. It asks five questions, shows you who your server
    says it is and asks you to confirm that, and then runs the one install command on the
    server over the SSH program that comes with Windows.

    What it never does:
      - It never asks for a password and never keeps one. When your server wants a
        password, the SSH program asks you for it itself.
      - It never saves what you type. The only file it writes is your server's public
        identity, in a temporary folder it deletes before it finishes.
      - It never reads the setup code. The installer prints that code in this window and
        you copy it from there.

    The guide for this file is docs/install/windows.md. The command it runs is held by
    brain.deployment.windows_helper, and tests/unit/test_windows_helper.py runs this script
    against a stand-in for SSH, in both of PowerShell's language modes.

    Written for Windows PowerShell 5.1, which every Windows 10 and 11 has, and for
    Constrained Language Mode, which is how Windows runs a script nobody signed when an
    application control policy is on: cmdlets and the SSH tools only, no .NET types.
#>

Set-StrictMode -Version 2.0

# The sizes the installer accepts, in its own words. tests/unit/test_windows_helper.py holds
# this list equal to brain.ops.wiring.PROFILES.
$BrainSizes = @('lite', 'standard', 'full')

$BrainSizeMeanings = @{
    'lite'     = 'the application and its database. The smallest, and where most companies start.'
    'standard' = 'adds background workers, a file store, a sign-in server and a local AI model.'
    'full'     = 'adds a trace ledger, an automation canvas and a record matcher.'
}

# The one file this writes: the server's public identity, in a folder of its own. A bare name
# rather than a path, because SSH splits an option's value on spaces and a Windows user folder
# can have a space in it. The script changes into that folder before it runs SSH.
$BrainKnownHosts = 'brain-known-hosts'

# How many times a question is asked before the helper stops, so a mistyped answer can be
# corrected and a helper with nobody answering it does not ask for ever.
$BrainTries = 5

# ---------------------------------------------------------------------- the answers' shapes

function Test-BrainHostName([string]$Text) {
    # An address SSH can be given as an argument and nothing else. Never beginning with a dash,
    # which SSH would read as an option: -oProxyCommand=... runs a program on this computer.
    if ($Text.Length -lt 1 -or $Text.Length -gt 253) { return $false }
    if ($Text -match '^[0-9.]+$') {
        if ($Text -notmatch '^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$') { return $false }
        foreach ($part in 1..4) {
            if ([int]$Matches[$part] -gt 255) { return $false }
        }
        return $true
    }
    if ($Text -match '^[0-9A-Fa-f:]+$') {
        return ($Text.Split(':').Count -ge 3)
    }
    return ($Text -match '^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$')
}

function Split-BrainServer([string]$Text) {
    # The address, and a port after a colon when there is one: server:2222, or [v6]:2222.
    $given = $Text.Trim()
    $name = $given
    $port = 22
    if ($given -match '^\[([0-9A-Fa-f:]+)\](:(\d{1,5}))?$') {
        $name = $Matches[1]
        if ($Matches[3]) { $port = [int]$Matches[3] }
    }
    elseif ($given -match '^([^:\[\]]+):(\d{1,5})$') {
        $name = $Matches[1]
        $port = [int]$Matches[2]
    }
    if ($port -lt 1 -or $port -gt 65535) { return $null }
    if (-not (Test-BrainHostName $name)) { return $null }
    return @{ Name = $name; Port = $port }
}

function Test-BrainUserName([string]$Text) {
    return ($Text -match '^[A-Za-z_][A-Za-z0-9_.-]{0,31}$')
}

function Get-BrainReleaseFiles([string]$Text) {
    # Where install.sh and the archive of one release are, from the address of the page they
    # were downloaded from: a release page, a link to one of its files, or a folder named for
    # the release. https only, because the command runs what it downloads as root.
    $given = $Text.Trim()
    if ($given -notmatch '^https://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~%+-]+)+/?$') {
        return $null
    }
    $address = $given.TrimEnd('/')
    if ($address -match '^(https://[^/]+/[^/]+/[^/]+/releases)/(tag|download)/([^/]+)(/[^/]+)?$') {
        $release = $Matches[3]
        $folder = $Matches[1] + '/download/' + $release
    }
    else {
        $release = $address.Substring($address.LastIndexOf('/') + 1)
        $folder = $address
    }
    if ($release -notmatch '^v[0-9][0-9A-Za-z.-]{0,62}$') { return $null }
    return @{
        Release    = $release
        ScriptUrl  = $folder + '/install.sh'
        ArchiveUrl = $folder + '/brain-' + $release + '.tar.gz'
    }
}

function Test-BrainConsoleAddress([string]$Text) {
    if ($Text -eq '') { return $true }
    return ($Text -match '^https?://[A-Za-z0-9.-]+(:\d{1,5})?(/[A-Za-z0-9._~%+-]+)*/?$')
}

# ---------------------------------------------------------------------- what SSH is asked

function New-BrainInstallCommand($Files, [string]$Size, [string]$ConsoleAddress) {
    # docs/install/install.md's command, minus reading the script first. Nothing is quoted
    # because every value has already been refused unless it cannot change the line.
    $fetch = 'curl -fsSL ' + $Files.ScriptUrl + ' -o install.sh'
    $run = 'sudo BRAIN_RELEASE_URL=' + $Files.ArchiveUrl + ' bash install.sh --release ' +
        $Files.Release + ' --profile ' + $Size
    if ($ConsoleAddress -ne '') {
        $run = $run + ' --console-address ' + $ConsoleAddress
    }
    return ($fetch + ' && ' + $run)
}

function New-BrainProbeArguments($Server, [string]$User) {
    # Asks the server who it is and offers it nothing: no key, no password. What it presents
    # is written into this helper's own file and nowhere else.
    return @(
        '-T',
        '-p', [string]$Server.Port,
        '-l', $User,
        '-o', 'BatchMode=yes',
        '-o', 'PubkeyAuthentication=no',
        '-o', 'PasswordAuthentication=no',
        '-o', 'KbdInteractiveAuthentication=no',
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', ('UserKnownHostsFile=' + $BrainKnownHosts),
        '-o', ('GlobalKnownHostsFile=' + $BrainKnownHosts),
        '-o', 'ConnectTimeout=15',
        '--', $Server.Name
    )
}

function New-BrainInstallArguments($Server, [string]$User, [string]$Command) {
    # The install connection accepts the key the person confirmed and no other.
    return @(
        '-t',
        '-p', [string]$Server.Port,
        '-l', $User,
        '-o', 'StrictHostKeyChecking=yes',
        '-o', ('UserKnownHostsFile=' + $BrainKnownHosts),
        '-o', ('GlobalKnownHostsFile=' + $BrainKnownHosts),
        '-o', 'UpdateHostKeys=no',
        '-o', 'ServerAliveInterval=30',
        '-o', 'ConnectTimeout=15',
        '--', $Server.Name, $Command
    )
}

function Get-BrainFingerprints([string]$KeyGen) {
    $found = @()
    if (-not (Test-Path -LiteralPath $BrainKnownHosts)) { return ,$found }
    $lines = & $KeyGen -l -f $BrainKnownHosts 2>$null
    foreach ($line in @($lines)) {
        if ("$line" -match '^\s*\d+\s+(SHA256:\S+)\s.*\(([A-Za-z0-9-]+)\)\s*$') {
            $found += ('    ' + $Matches[2] + '  ' + $Matches[1])
        }
    }
    return ,$found
}

function Get-BrainReachProblem([string]$Said) {
    if ($Said -match 'resolve hostname|not known|No such host') {
        return 'That address could not be found. Check it for typing mistakes.'
    }
    if ($Said -match 'timed out') {
        return 'The server did not answer. Check the address, and that the server is switched on.'
    }
    if ($Said -match 'refused') {
        return 'The server refused the connection. SSH may not be running there, or it may use another port: type the address as address:port.'
    }
    return 'The server could not be reached.'
}

# ---------------------------------------------------------------------- asking

function Read-BrainAnswer([string]$Question) {
    $answer = Read-Host $Question
    if ($null -eq $answer) { return $null }
    return $answer.Trim()
}

function Stop-Brain([string]$Why) {
    Write-Host ''
    Write-Host $Why
    Write-Host 'Nothing was installed.'
    $script:BrainExitCode = 1
}

function Invoke-BrainHelper {
    $script:BrainExitCode = 1
    Write-Host ''
    Write-Host 'Install Company Brain on your server'
    Write-Host '------------------------------------'
    Write-Host 'This asks you five questions, checks who your server is with you, and then runs'
    Write-Host 'the install on the server. Nothing you type is saved on this computer.'
    Write-Host ''

    $ssh = @(Get-Command ssh -CommandType Application -ErrorAction SilentlyContinue)
    $keygen = @(Get-Command ssh-keygen -CommandType Application -ErrorAction SilentlyContinue)
    if ($ssh.Count -eq 0 -or $keygen.Count -eq 0) {
        Stop-Brain ('The SSH program that comes with Windows is not switched on. Open Settings, ' +
            'then System, then Optional features, add OpenSSH Client, and run this again.')
        return
    }
    $sshPath = $ssh[0].Path
    $keygenPath = $keygen[0].Path

    # 1. The server.
    $server = $null
    foreach ($try in 1..$BrainTries) {
        Write-Host '1. What is your server''s address? This is the name, or the four numbers with'
        Write-Host '   dots between them, that your hosting company gave you.'
        $answer = Read-BrainAnswer '   Address'
        if ($null -eq $answer) { break }
        $server = Split-BrainServer $answer
        if ($null -ne $server) { break }
        Write-Host '   That is not an address this can use. Type only the address, with no spaces,'
        Write-Host '   and with no user name or web address in front of it.'
        Write-Host ''
    }
    if ($null -eq $server) { Stop-Brain 'No usable server address was given.'; return }
    Write-Host ''

    # 2. The user name.
    $user = $null
    foreach ($try in 1..$BrainTries) {
        Write-Host '2. What user name do you sign in to the server with? Press Enter for root.'
        $answer = Read-BrainAnswer '   User name'
        if ($null -eq $answer) { break }
        if ($answer -eq '') { $answer = 'root' }
        if (Test-BrainUserName $answer) { $user = $answer; break }
        Write-Host '   That is not a user name a server can have. Use letters, digits, dots,'
        Write-Host '   dashes and underscores only.'
        Write-Host ''
    }
    if ($null -eq $user) { Stop-Brain 'No usable user name was given.'; return }
    Write-Host ''

    # 3. The release.
    $files = $null
    foreach ($try in 1..$BrainTries) {
        Write-Host '3. Which release? Open the release page you downloaded this helper from, copy'
        Write-Host '   the address from the top of your browser, and paste it here.'
        $answer = Read-BrainAnswer '   Release page'
        if ($null -eq $answer) { break }
        $files = Get-BrainReleaseFiles $answer
        if ($null -ne $files) { break }
        Write-Host '   That is not a release address this can use. Copy all of it from the address'
        Write-Host '   bar: it starts with https and ends with the release name, like v1.0.0.'
        Write-Host ''
    }
    if ($null -eq $files) { Stop-Brain 'No usable release address was given.'; return }
    Write-Host ('   Release: ' + $files.Release)
    Write-Host ''

    # 4. The size.
    $size = $null
    foreach ($try in 1..$BrainTries) {
        Write-Host '4. Which size? Type one of these names:'
        foreach ($one in $BrainSizes) {
            Write-Host ('     ' + $one + ': ' + $BrainSizeMeanings[$one])
        }
        $answer = Read-BrainAnswer '   Size'
        if ($null -eq $answer) { break }
        if ($BrainSizes -ccontains $answer.ToLower()) { $size = $answer.ToLower(); break }
        Write-Host '   Type one of the three names exactly.'
        Write-Host ''
    }
    if ($null -eq $size) { Stop-Brain 'No size was chosen.'; return }
    Write-Host ''

    # 5. The console address.
    $console = $null
    foreach ($try in 1..$BrainTries) {
        Write-Host '5. What web address will your staff open Company Brain at, for example'
        Write-Host '   https://brain.example.invalid? If you do not know yet, press Enter.'
        $answer = Read-BrainAnswer '   Web address'
        if ($null -eq $answer) { break }
        if (Test-BrainConsoleAddress $answer) { $console = $answer; break }
        Write-Host '   That is not a whole web address. Type all of it, starting with https and a colon.'
        Write-Host ''
    }
    if ($null -eq $console) { Stop-Brain 'No usable web address was given.'; return }
    Write-Host ''

    $command = New-BrainInstallCommand $files $size $console
    $workspace = New-TemporaryFile
    Remove-Item -LiteralPath $workspace.FullName -Force
    $folder = New-Item -ItemType Directory -Path $workspace.FullName
    Push-Location -LiteralPath $folder.FullName
    try {
        Write-Host ('Asking ' + $server.Name + ' who it is. Nothing is sent to it yet.')
        $probe = New-BrainProbeArguments $server $user
        $said = (& $sshPath @probe 2>&1 | ForEach-Object { "$_" }) -join ' '
        $fingerprints = Get-BrainFingerprints $keygenPath
        if ($fingerprints.Count -eq 0) {
            Write-Host ''
            Write-Host (Get-BrainReachProblem $said)
            Write-Host 'Nothing was installed.'
            $script:BrainExitCode = 2
            return
        }

        Write-Host ''
        Write-Host 'Your server says its identity is:'
        foreach ($one in $fingerprints) { Write-Host $one }
        Write-Host ''
        Write-Host 'This is how you know you are talking to your own server and not to something'
        Write-Host 'pretending to be it. If your hosting company showed you a fingerprint for this'
        Write-Host 'server, check it is the same as the one above. If you created the server'
        Write-Host 'yourself a short while ago and have nothing to compare it with, it is usual'
        Write-Host 'to go on.'
        $answer = Read-BrainAnswer 'Type yes if it matches, or anything else to stop'
        if ($answer -ne 'yes') { Stop-Brain 'You did not confirm the server.'; return }

        Write-Host ''
        Write-Host ('About to install release ' + $files.Release + ', size ' + $size + ', on ' +
            $server.Name + ' as ' + $user + '.')
        Write-Host 'The server may ask for your password, perhaps twice: once to sign in and once'
        Write-Host 'to install. Type it when asked. The install takes several minutes.'
        if ($console -eq '') {
            Write-Host 'The installer may ask about the web address again. Press Enter if it does.'
        }
        $answer = Read-BrainAnswer 'Type yes to start'
        if ($answer -ne 'yes') { Stop-Brain 'You did not start the install.'; return }
        Write-Host ''

        $install = New-BrainInstallArguments $server $user $command
        & $sshPath @install
        $finished = $LASTEXITCODE

        Write-Host ''
        if ($finished -ne 0) {
            Write-Host 'The install stopped before it finished. The last lines above say what went'
            Write-Host 'wrong and what to do. When it is fixed, run this helper again: the install'
            Write-Host 'is safe to run twice.'
            $script:BrainExitCode = 2
            return
        }
        Write-Host 'The install finished.'
        Write-Host ''
        Write-Host 'Look a few lines up for the line that begins with: setup code:'
        Write-Host 'Copy the long code on that line. You need it on the first screen of setup.'
        if ($console -ne '') {
            Write-Host ('Then open ' + $console.TrimEnd('/') + '/first-run in your web browser, sign in, and')
            Write-Host 'enter the code. Until somebody does, whoever opens that address first becomes'
            Write-Host 'the administrator, so do it now.'
        }
        else {
            Write-Host 'Then open /first-run on your web address, sign in, and enter the code. Until'
            Write-Host 'somebody does, whoever opens that address first becomes the administrator.'
        }
        $script:BrainExitCode = 0
    }
    finally {
        Pop-Location
        Remove-Item -LiteralPath $folder.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Dot-sourcing this file loads the functions above and asks nothing, which is how the tests
# reach them one at a time.
if ($MyInvocation.InvocationName -ne '.') {
    $script:BrainExitCode = 1
    Invoke-BrainHelper
    Write-Host ''
    [void](Read-Host 'Press Enter to close this window')
    exit $script:BrainExitCode
}
