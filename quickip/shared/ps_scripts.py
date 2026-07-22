"""Shared PowerShell script builders.

Scripts are stored as readable multi-line strings and collapsed to a single line
before passing to PowerShell (-Command). This keeps them readable in code while
remaining compatible with the -Command parameter that requires no newlines.
"""

import textwrap


def _collapse(script: str) -> str:
    """Collapse a multi-line PowerShell script to a single line for -Command."""
    # Strip indentation, join lines with semicolon where needed
    lines = [ln.strip() for ln in textwrap.dedent(script).splitlines() if ln.strip()]
    return " ".join(lines)


def build_net_adapters_ps(include_media: bool = False) -> str:
    """Return a PowerShell one-liner that queries all network adapters as JSON.

    Args:
        include_media: When True, adds the MediaType field (needed by the
                       Tools → Current Networks view).
    """
    media_select = ",MediaType" if include_media else ""
    media_prop = (
        "Media=$a.MediaType; Mac=$a.MacAddress; Speed=$a.LinkSpeed;"
        if include_media else
        "Mac=$a.MacAddress; Speed=$a.LinkSpeed;"
    )

    script = f"""
        $adapters = Get-NetAdapter |
            Select-Object Name,InterfaceDescription,Status,MacAddress,LinkSpeed{media_select},InterfaceIndex;
        $ips = Get-NetIPAddress |
            Select-Object InterfaceIndex,IPAddress,PrefixLength,AddressFamily,PrefixOrigin;
        $gws = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue |
            Select-Object InterfaceIndex,NextHop;
        $dns_map = @{{}};
        (Get-DnsClientServerAddress -ErrorAction SilentlyContinue) | ForEach-Object {{
            $dns_map[$_.InterfaceIndex] = $_.ServerAddresses -join ', '
        }};
        $result = foreach ($a in $adapters) {{
            $idx = $a.InterfaceIndex;
            $ip4 = ($ips | Where-Object {{
                $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 2
            }} | Select-Object -First 1);
            $ip6 = ($ips | Where-Object {{
                $_.InterfaceIndex -eq $idx -and $_.AddressFamily -eq 23
            }} | Select-Object -First 1);
            $gw = ($gws | Where-Object {{
                $_.InterfaceIndex -eq $idx
            }} | Select-Object -First 1);
            [PSCustomObject]@{{
                Name        = $a.Name;
                Description = $a.InterfaceDescription;
                Status      = $a.Status;
                {media_prop}
                IPv4    = if ($ip4) {{ $ip4.IPAddress }}   else {{ '' }};
                Prefix  = if ($ip4) {{ [int]$ip4.PrefixLength }} else {{ 0 }};
                IPv6    = if ($ip6) {{ $ip6.IPAddress }}   else {{ '' }};
                Gateway = if ($gw)  {{ $gw.NextHop }}      else {{ '' }};
                DNS     = if ($dns_map[$idx]) {{ $dns_map[$idx] }} else {{ '' }};
                DHCP    = if ($ip4) {{ $ip4.PrefixOrigin }} else {{ '' }};
            }}
        }};
        $result | ConvertTo-Json -Compress
    """
    return _collapse(script)
