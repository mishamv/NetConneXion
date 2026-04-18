"""Shared PowerShell script builders."""


def build_net_adapters_ps(include_media: bool = False) -> str:
    """Return a PowerShell script that queries all network adapters.

    Args:
        include_media: When True, adds the MediaType field (needed by the
                       Tools → Current Networks view).
    """
    select_extra = ",MediaType" if include_media else ""
    media_prop = (
        "    Mac=$a.MacAddress; Speed=$a.LinkSpeed; Media=$a.MediaType;"
        if include_media else
        "    Mac=$a.MacAddress; Speed=$a.LinkSpeed;"
    )

    head = (
        "$adapters = Get-NetAdapter | Select-Object Name,InterfaceDescription,"
        "Status,MacAddress,LinkSpeed"
    )
    head += select_extra + ",InterfaceIndex;"

    body = (
        "$ips = Get-NetIPAddress | Select-Object InterfaceIndex,IPAddress,"
        "PrefixLength,AddressFamily,PrefixOrigin;"
        "$gws = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue"
        " | Select-Object InterfaceIndex,NextHop;"
        "$dns_map = @{};"
        "(Get-DnsClientServerAddress -ErrorAction SilentlyContinue) | ForEach-Object {"
        "  $dns_map[$_.InterfaceIndex] = $_.ServerAddresses -join ', '};"
        "$result = foreach ($a in $adapters) {"
        "  $idx = $a.InterfaceIndex;"
        "  $ip4 = ($ips | Where-Object {"
        "    $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 2} | Select-Object -First 1);"
        "  $ip6 = ($ips | Where-Object {"
        "    $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 23} | Select-Object -First 1);"
        "  $gw = ($gws | Where-Object {$_.InterfaceIndex -eq $idx} | Select-Object -First 1);"
        "  [PSCustomObject]@{"
        "    Name=$a.Name; Description=$a.InterfaceDescription; Status=$a.Status;"
    )

    tail = (
        "    IPv4=if($ip4){$ip4.IPAddress}else{''};"
        "    Prefix=if($ip4){[int]$ip4.PrefixLength}else{0};"
        "    IPv6=if($ip6){$ip6.IPAddress}else{''};"
        "    Gateway=if($gw){$gw.NextHop}else{''};"
        "    DNS=if($dns_map[$idx]){$dns_map[$idx]}else{''};"
        "    DHCP=if($ip4){$ip4.PrefixOrigin}else{''}}};"
        "$result | ConvertTo-Json -Compress"
    )

    return head + body + media_prop + tail
