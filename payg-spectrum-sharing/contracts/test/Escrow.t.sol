// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Escrow.sol";
import "../src/MockERC20.sol";

contract EscrowTest is Test {
    Escrow escrow;
    MockERC20 token;

    address issuerB = address(0xB1);
    address bm = address(0xB2);
    bytes32 sid = keccak256("session-1");
    uint64 L = 10;
    uint256 price = 1 ether;

    function setUp() public {
        escrow = new Escrow();
        token = new MockERC20("Mock", "MCK");
        token.mint(issuerB, 10_000 ether);
        vm.startPrank(issuerB);
        token.approve(address(escrow), type(uint256).max);
        vm.stopPrank();
    }

    function buildChain(bytes32 _sid, uint64 _L) internal pure returns (bytes32[] memory ys) {
        ys = new bytes32[](_L + 1);
        ys[_L] = keccak256("yL");
        for (uint64 idx = _L; idx > 0; idx--) {
            ys[idx - 1] = sha256(abi.encodePacked(_sid, idx - 1, ys[idx]));
        }
    }

    function testOpenClaimCloseHappyPath() public {
        bytes32[] memory ys = buildChain(sid, L);
        uint256 deposit = price * L;
        uint64 expB = uint64(block.timestamp + 1 days);
        vm.prank(issuerB);
        escrow.openSession(
            sid,
            bm,
            address(token),
            hex"01",
            L,
            expB,
            price,
            deposit,
            ys[0]
        );

        // BM claims up to beat 3
        vm.prank(bm);
        escrow.claim(sid, 3, ys[3]);
        assertEq(token.balanceOf(bm), 3 * price);

        // BM claims up to beat 5
        vm.prank(bm);
        escrow.claim(sid, 5, ys[5]);
        assertEq(token.balanceOf(bm), 5 * price);

        // Close and refund remainder to issuerB
        vm.warp(uint256(expB) + 1);
        vm.prank(issuerB);
        escrow.closeSession(sid);
        assertEq(token.balanceOf(issuerB), 10_000 ether - 5 * price);
    }

    function testDepositExactAndClaimToLimit() public {
        uint64 lLocal = 3;
        bytes32[] memory ys = buildChain(sid, lLocal);
        uint256 priceLocal = 2 ether;
        uint256 deposit = priceLocal * lLocal; // exact funding
        uint64 expB = uint64(block.timestamp + 1 days);

        vm.prank(issuerB);
        escrow.openSession(
            sid,
            bm,
            address(token),
            hex"01",
            lLocal,
            expB,
            priceLocal,
            deposit,
            ys[0]
        );

        vm.prank(bm);
        escrow.claim(sid, lLocal, ys[lLocal]);
        assertEq(token.balanceOf(bm), lLocal * priceLocal);

        vm.warp(uint256(expB) + 1);
        vm.prank(issuerB);
        escrow.closeSession(sid);
        // No refund expected
        assertEq(token.balanceOf(issuerB), 10_000 ether - deposit);
    }

    function testRejectReplayOrOverclaim() public {
        bytes32[] memory ys = buildChain(sid, 5);
        uint256 deposit = price * 5;
        vm.prank(issuerB);
        escrow.openSession(
            sid,
            bm,
            address(token),
            hex"01",
            5,
            0,
            price,
            deposit,
            ys[0]
        );

        vm.prank(bm);
        escrow.claim(sid, 2, ys[2]);
        assertEq(token.balanceOf(bm), 2 * price);

        vm.prank(bm);
        vm.expectRevert(Escrow.NonMonotonic.selector);
        escrow.claim(sid, 2, ys[2]);

        vm.prank(bm);
        vm.expectRevert(bytes("beyond limit"));
        escrow.claim(sid, 10, ys[5]);
    }

    function testOnlyIssuerBCanClose() public {
        bytes32[] memory ys = buildChain(sid, 3);
        uint256 deposit = price * 3;
        uint64 expB = uint64(block.timestamp + 1 days);
        vm.prank(issuerB);
        escrow.openSession(
            sid,
            bm,
            address(token),
            hex"01",
            3,
            expB,
            price,
            deposit,
            ys[0]
        );

        vm.prank(bm);
        vm.expectRevert(Escrow.NotIssuerB.selector);
        escrow.closeSession(sid);
    }

    function testIssuerBCannotCloseBeforeExpB() public {
        bytes32[] memory ys = buildChain(sid, 3);
        uint256 deposit = price * 3;
        uint64 expB = uint64(block.timestamp + 1 days);

        vm.prank(issuerB);
        escrow.openSession(
            sid,
            bm,
            address(token),
            hex"01",
            3,
            expB,
            price,
            deposit,
            ys[0]
        );

        vm.prank(issuerB);
        vm.expectRevert(Escrow.ExpiryNotReached.selector);
        escrow.closeSession(sid);
    }

    function testClaimGap10() public {
        bytes32 sid10 = keccak256("session-gap-10");
        uint64 lLocal = 120;
        bytes32[] memory ys = buildChain(sid10, lLocal);
        uint256 deposit = price * lLocal;
        vm.prank(issuerB);
        escrow.openSession(
            sid10,
            bm,
            address(token),
            hex"01",
            lLocal,
            0,
            price,
            deposit,
            ys[0]
        );
        vm.prank(bm);
        escrow.claim(sid10, 10, ys[10]);
    }

    function testClaimGap50() public {
        bytes32 sid50 = keccak256("session-gap-50");
        uint64 lLocal = 120;
        bytes32[] memory ys = buildChain(sid50, lLocal);
        uint256 deposit = price * lLocal;
        vm.prank(issuerB);
        escrow.openSession(
            sid50,
            bm,
            address(token),
            hex"01",
            lLocal,
            0,
            price,
            deposit,
            ys[0]
        );
        vm.prank(bm);
        escrow.claim(sid50, 50, ys[50]);
    }

    function testClaimGap100() public {
        bytes32 sid100 = keccak256("session-gap-100");
        uint64 lLocal = 120;
        bytes32[] memory ys = buildChain(sid100, lLocal);
        uint256 deposit = price * lLocal;
        vm.prank(issuerB);
        escrow.openSession(
            sid100,
            bm,
            address(token),
            hex"01",
            lLocal,
            0,
            price,
            deposit,
            ys[0]
        );
        vm.prank(bm);
        escrow.claim(sid100, 100, ys[100]);
    }
}
