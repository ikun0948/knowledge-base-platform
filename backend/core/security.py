"""口令哈希与会话令牌：只用标准库，不引 bcrypt/PyJWT（spec 4 节）。

为什么是 pbkdf2 而不是 sha256 直哈希：口令短、字符集小，快哈希能被暴力枚举，
慢哈希 + 随机盐把"库泄露 = 全库口令泄露"降级成"每条各自硬算上亿次"。
为什么库里存令牌的 SHA-256 而不是令牌本身：令牌就是凭证原文，拖库者拿到即能登录；
哈希过之后那行数据本身不可用，服务端只需要"算一遍再比对"。
"""
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """坏行只说"不对"，不抛：库里一行被手改过不该把登录接口打成 500。"""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError, AttributeError):
        return False
    # compare_digest 而不是 ==：普通字符串比较在第一个不同字节就返回，
    # 逐字节耗时差能把"猜对了几位"读出来
    return hmac.compare_digest(expected.hex(), digest_hex)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
