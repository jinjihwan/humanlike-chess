# Do not echo or persist LICHESS_TOKEN.
if (-not $env:LICHESS_TOKEN) {
    Write-Output 'LICHESS_TOKEN is missing in this PowerShell session.'
    exit 1
}
$headers = @{ Authorization = "Bearer $env:LICHESS_TOKEN" }
$requests = @(
    @{ Name='Account'; Url='https://lichess.org/api/account' },
    @{ Name='Explorer play'; Url='https://explorer.lichess.org/lichess?variant=standard&play=d2d4&ratings=1400&speeds=blitz&moves=8&topGames=0&recentGames=0' },
    @{ Name='Explorer fen'; Url='https://explorer.lichess.org/lichess?variant=standard&fen=rnbqkbnr%2Fpppppppp%2F8%2F8%2F3P4%2F8%2FPPP1PPPP%2FRNBQKBNR%20b%20KQkq%20-%200%201&ratings=1400&speeds=blitz&moves=8&topGames=0&recentGames=0' }
)
foreach ($req in $requests) {
    try {
        $response = Invoke-WebRequest -Uri $req.Url -Headers $headers -Method Get -TimeoutSec 25 -UseBasicParsing
        Write-Output "$($req.Name): HTTP $([int]$response.StatusCode)"
    } catch {
        $code = 'unknown'
        if ($_.Exception.Response) {
            try { $code = [int]$_.Exception.Response.StatusCode } catch {}
        }
        Write-Output "$($req.Name): HTTP $code ($($_.Exception.GetType().Name))"
    }
}
