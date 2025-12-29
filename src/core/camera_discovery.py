import socket
import time
import ipaddress
from typing import List, Set

WS_DISCOVERY_ADDR = "239.255.255.250"
WS_DISCOVERY_PORT = 3702

WS_PROBE = (
    """
    <?xml version=\"1.0\" encoding=\"UTF-8\"?>
    <e:Envelope xmlns:e=\"http://www.w3.org/2003/05/soap-envelope\" xmlns:w=\"http://schemas.xmlsoap.org/ws/2004/09/mex\" xmlns:d=\"http://schemas.xmlsoap.org/ws/2005/04/discovery\" xmlns:dn=\"http://www.onvif.org/ver10/network/wsdl\">
      <e:Header>
        <d:Probe xmlns:d=\"http://schemas.xmlsoap.org/ws/2005/04/discovery\">
          <d:Types>dn:NetworkVideoTransmitter</d:Types>
        </d:Probe>
      </e:Header>
      <e:Body/>
    </e:Envelope>
    """
).strip()


def _parse_ips(raw_xml: bytes) -> Set[str]:
    text = raw_xml.decode("utf-8", errors="ignore")
    ips: Set[str] = set()
    for token in text.split():
        try:
            ipaddress.ip_address(token)
            ips.add(token)
        except ValueError:
            continue
    # crude extraction from XAddrs
    if "XAddrs" in text:
        parts = text.split("XAddrs")
        for p in parts[1:]:
            start = p.find(">")
            end = p.find("<", start + 1)
            if start != -1 and end != -1:
                urls = p[start + 1 : end].split()
                for url in urls:
                    host_part = url.split("//", 1)[-1].split("/", 1)[0]
                    host = host_part.split(":")[0]
                    try:
                        ipaddress.ip_address(host)
                        ips.add(host)
                    except ValueError:
                        pass
    return ips


class CameraDiscovery:
    def __init__(self, scan_subnets: List[str], ws_enabled: bool = True, timeout: float = 2.0) -> None:
        self.scan_subnets = scan_subnets
        self.ws_enabled = ws_enabled
        self.timeout = timeout

    def discover_ips(self) -> Set[str]:
        ips: Set[str] = set()
        if self.ws_enabled:
            ips.update(self._ws_discovery())
        for subnet in self.scan_subnets or []:
            ips.update(self._scan_rtsp_subnet(subnet))
        return ips

    def _ws_discovery(self) -> Set[str]:
        ips: Set[str] = set()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.settimeout(self.timeout)
            sock.sendto(WS_PROBE.encode("utf-8"), (WS_DISCOVERY_ADDR, WS_DISCOVERY_PORT))
            start = time.time()
            while time.time() - start < self.timeout:
                try:
                    data, _ = sock.recvfrom(65535)
                    ips.update(_parse_ips(data))
                except socket.timeout:
                    break
        finally:
            sock.close()
        return ips

    def _scan_rtsp_subnet(self, cidr: str) -> Set[str]:
        ips: Set[str] = set()
        try:
            network = ipaddress.ip_network(cidr, strict=False)
        except ValueError:
            return ips
        for ip in network.hosts():
            ip_str = str(ip)
            if self._is_port_open(ip_str, 554, 0.3):
                ips.add(ip_str)
        return ips

    @staticmethod
    def _is_port_open(host: str, port: int, timeout: float) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False
