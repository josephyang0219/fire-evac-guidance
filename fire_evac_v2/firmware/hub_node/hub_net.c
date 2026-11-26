// hub_net.c -- HTTP POST over a raw lwIP socket with a hard time limit (FW 2.8, 2026-11-26).
//
// Why not WiFiClient: the SDK client (cores/ambpro2/ard_socket.c start_client) connects with a plain blocking
// connect() (no time limit) and sets SO_SNDTIMEO to 30 s, so with a busy hotspot one client.write() of a 15 KB snapshot
// could hold loop() for tens of seconds or more (11-26: three of four boards went silent with the camera wall open and
// the 60 s software watchdog at the end of loop() never ran). Here every step gets what is left of one budget:
// connect (non-blocking + select), send in TCP_MSS pieces (SO_SNDTIMEO = time left, re-set before each piece),
// receive (SO_RCVTIMEO = time left). Out of time -> the socket is closed and the caller sees a failure.
//
// Kept in a .c file on purpose: lwip/sockets.h defines connect/send/read/write/close as macros, which would break the
// Arduino objects (client.write, Serial.read ...) if it were included in the sketch.
#include <lwip/sockets.h>
#include <lwip/sys.h>
#include <string.h>
#include "hub_net.h"

#define HUB_NET_PIECE 1460                 // one TCP segment (TCP_MSS in the SDK's lwipopts.h)

static int msLeft(uint32_t t0, uint32_t budget) {
  uint32_t used = sys_now() - t0;
  return used >= budget ? 0 : (int)(budget - used);
}

static int setTimeout(int s, int opt, int ms) {     // LWIP_SO_SNDRCVTIMEO_NONSTANDARD = 1: the value is an int in ms
  if (ms < 1) ms = 1;
  return lwip_setsockopt(s, SOL_SOCKET, opt, &ms, sizeof(ms));
}

static int connectWithin(uint32_t ip, uint16_t port, uint32_t t0, uint32_t budget) {
  int s = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (s < 0) return -1;
  int flags = lwip_fcntl(s, F_GETFL, 0);
  lwip_fcntl(s, F_SETFL, flags | O_NONBLOCK);
  struct sockaddr_in a;
  memset(&a, 0, sizeof(a));
  a.sin_family = AF_INET; a.sin_port = htons(port); a.sin_addr.s_addr = ip;   // ip as IPAddress gives it (network order)
  if (lwip_connect(s, (struct sockaddr*)&a, sizeof(a)) != 0) {
    int ms = msLeft(t0, budget);
    fd_set w; FD_ZERO(&w); FD_SET(s, &w);
    struct timeval tv; tv.tv_sec = ms / 1000; tv.tv_usec = (ms % 1000) * 1000;
    int err = 1; socklen_t el = sizeof(err);
    if (ms <= 0 || lwip_select(s + 1, NULL, &w, NULL, &tv) <= 0 ||
        lwip_getsockopt(s, SOL_SOCKET, SO_ERROR, &err, &el) != 0 || err != 0) { lwip_close(s); return -1; }
  }
  lwip_fcntl(s, F_SETFL, flags & ~O_NONBLOCK);       // back to blocking: send/recv are bounded by the timeouts below
  int one = 1;
  lwip_setsockopt(s, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
  return s;
}

static int sendWithin(int s, const uint8_t* p, uint32_t len, uint32_t t0, uint32_t budget) {
  while (len) {
    int ms = msLeft(t0, budget);
    if (ms <= 0) return -1;
    setTimeout(s, SO_SNDTIMEO, ms);
    int n = lwip_send(s, p, len > HUB_NET_PIECE ? HUB_NET_PIECE : len, 0);
    if (n <= 0) return -1;
    p += n; len -= (uint32_t)n;
  }
  return 0;
}

int hub_http_post(uint32_t ip, uint16_t port, const char* head, uint32_t headLen, const uint8_t* body, uint32_t bodyLen,
                  char* out, int outMax, uint32_t budgetMs) {
  uint32_t t0 = sys_now();
  int got = 0;
  if (outMax > 0) out[0] = 0;
  int s = connectWithin(ip, port, t0, budgetMs);
  if (s < 0) return HUB_NET_CONNECT;
  if (sendWithin(s, (const uint8_t*)head, headLen, t0, budgetMs) || (bodyLen && sendWithin(s, body, bodyLen, t0, budgetMs))) {
    lwip_close(s); return HUB_NET_SEND;
  }
  while (got < outMax - 1) {                         // Connection: close -> the server ends the reply by closing
    int ms = msLeft(t0, budgetMs);
    if (ms <= 0) break;
    setTimeout(s, SO_RCVTIMEO, ms);
    int n = lwip_recv(s, out + got, outMax - 1 - got, 0);
    if (n <= 0) break;
    got += n;
  }
  if (outMax > 0) out[got] = 0;
  lwip_close(s);
  return got;
}
