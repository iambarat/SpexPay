// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

/// @title PAYG Escrow (simplified scaffold)
/// @notice Holds deposits from IssuerB and pays Band Manager based on monotonic heartbeat claims.
contract Escrow {
    struct Session {
        address issuerB;
        address bm;
        address asset;
        bytes pkSession;
        uint64 lastI;
        bytes32 lastY;
        uint64 L;
        uint64 expB;
        uint256 pricePerBeat;
        uint256 deposit;
        bool closed;
    }

    mapping(bytes32 => Session) public sessions;

    event SessionOpened(bytes32 indexed sid, address indexed issuerB, address indexed bm, uint256 deposit);
    event Claimed(bytes32 indexed sid, uint64 i, uint256 paid);
    event SessionClosed(bytes32 indexed sid, uint256 refund);

    error InvalidSession();
    error AlreadyExists();
    error NotIssuerB();
    error AlreadyClosed();
    error NonMonotonic();
    error InsufficientDeposit();

    function openSession(
        bytes32 sid,
        address bm,
        address asset,
        bytes calldata pkSession,
        uint64 L,
        uint64 expB,
        uint256 pricePerBeat,
        uint256 deposit,
        bytes32 y0
    ) external {
        if (sessions[sid].issuerB != address(0)) revert AlreadyExists();
        uint256 requiredDeposit = pricePerBeat * uint256(L);
        require(deposit >= requiredDeposit, "deposit < pricePerBeat * L");
        sessions[sid] = Session({
            issuerB: msg.sender,
            bm: bm,
            asset: asset,
            pkSession: pkSession,
            lastI: 0,
            lastY: y0,
            L: L,
            expB: expB,
            pricePerBeat: pricePerBeat,
            deposit: deposit,
            closed: false
        });
        require(IERC20(asset).transferFrom(msg.sender, address(this), deposit), "transferFrom failed");
        emit SessionOpened(sid, msg.sender, bm, deposit);
    }

    /// @notice BM submits the latest heartbeat index and hash-chain head.
    function claim(bytes32 sid, uint64 i, bytes32 yi /*, bytes calldata sigma*/) external {
        Session storage s = sessions[sid];
        if (s.issuerB == address(0)) revert InvalidSession();
        if (s.closed) revert AlreadyClosed();
        if (msg.sender != s.bm) revert InvalidSession();
        if (i <= s.lastI) revert NonMonotonic();
        require(i <= s.L, "beyond limit");

        // Verify hash chain backward from yi to stored lastY.
        bytes32 acc = yi;
        for (uint64 idx = i; idx > s.lastI; idx--) {
            acc = sha256(abi.encodePacked(sid, idx - 1, acc));
        }
        require(acc == s.lastY, "hash chain mismatch");

        uint256 beats = i - s.lastI;
        uint256 pay = beats * s.pricePerBeat;
        if (pay > s.deposit) revert InsufficientDeposit();

        s.lastI = i;
        s.lastY = yi;
        s.deposit -= pay;
        require(IERC20(s.asset).transfer(s.bm, pay), "pay failed");
        emit Claimed(sid, i, pay);
    }

    function closeSession(bytes32 sid) external {
        Session storage s = sessions[sid];
        if (s.issuerB == address(0)) revert InvalidSession();
        if (s.closed) revert AlreadyClosed();
        if (msg.sender != s.issuerB) revert NotIssuerB();
        s.closed = true;
        uint256 refund = s.deposit;
        s.deposit = 0;
        if (refund > 0) {
            require(IERC20(s.asset).transfer(s.issuerB, refund), "refund failed");
        }
        emit SessionClosed(sid, refund);
    }
}
