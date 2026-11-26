// hub_net.h -- see hub_net.c: HTTP POST with one hard time limit for connect + send + receive.
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

#define HUB_NET_CONNECT (-1)   // could not connect within the budget
#define HUB_NET_SEND    (-2)   // connected, but the request did not go out within the budget

// Sends head (the HTTP request line + headers) and body to ip:port (ip as IPAddress converts it), then reads the reply
// into out (NUL-terminated, at most outMax-1 bytes) until the server closes or the budget runs out.
// Returns the reply length (>= 0) or HUB_NET_CONNECT / HUB_NET_SEND. Never takes much longer than budgetMs.
int hub_http_post(uint32_t ip, uint16_t port, const char* head, uint32_t headLen, const uint8_t* body, uint32_t bodyLen,
                  char* out, int outMax, uint32_t budgetMs);

#ifdef __cplusplus
}
#endif
