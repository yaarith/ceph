// -*- mode:C++; tab-width:8; c-basic-offset:2; indent-tabs-mode:t -*-
// vim: ts=8 sw=2 smarttab

#pragma once

#include <cstdint>
#include <string>
#include <tuple>
#include <vector>
#include "include/buffer_fwd.h"
#include "crimson/net/Fwd.h"

class CryptoKey;

namespace ceph::auth {

class error : public std::logic_error {
public:
  using std::logic_error::logic_error;
};

using method_t = uint32_t;

// TODO: revisit interfaces for non-dummy implementations
class AuthClient {
public:
  virtual ~AuthClient() {}

  /// Build an authentication request to begin the handshake
  ///
  /// @throw auth::error if unable to build the request
  virtual std::tuple<method_t,		     // auth method
		     std::vector<uint32_t>,  // preferred modes
		     ceph::bufferlist>	     // auth bl
  get_auth_request(ceph::net::ConnectionRef conn,
		   AuthConnectionMetaRef auth_meta) = 0;

  /// Handle server's request to continue the handshake
  ///
  /// @throw auth::error if unable to build the request
  virtual ceph::bufferlist handle_auth_reply_more(
    ceph::net::ConnectionRef conn,
    AuthConnectionMetaRef auth_meta,
    const ceph::bufferlist& bl) = 0;

  /// Handle server's indication that authentication succeeded
  ///
  /// @return 0 if authenticated, a negative number otherwise
  virtual int handle_auth_done(
    ceph::net::ConnectionRef conn,
    AuthConnectionMetaRef auth_meta,
    uint64_t global_id,
    uint32_t con_mode,
    const bufferlist& bl) = 0;

  /// Handle server's indication that the previous auth attempt failed
  ///
  /// @return 0 if will try next auth method, a negative number if we have no
  ///         more options
  virtual int handle_auth_bad_method(
    ceph::net::ConnectionRef conn,
    AuthConnectionMetaRef auth_meta,
    uint32_t old_auth_method,
    int result,
    const std::vector<uint32_t>& allowed_methods,
    const std::vector<uint32_t>& allowed_modes) = 0;
};

} // namespace ceph::auth
