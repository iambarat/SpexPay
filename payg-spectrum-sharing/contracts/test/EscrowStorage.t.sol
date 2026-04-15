// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Escrow.sol";
import "../src/MockERC20.sol";

contract EscrowStorageTest is Test {
    Escrow escrow;
    MockERC20 token;

    address issuerB = address(0xB1);
    address bm = address(0xB2);
    bytes32 sid = keccak256("storage-session-1");
    uint64 L = 10;
    uint256 price = 1 ether;
    uint256 deposit = price * L;

    function setUp() public {
        escrow = new Escrow();
        token = new MockERC20("Mock", "MCK");
        token.mint(issuerB, 10_000 ether);
    }

    function buildChain(bytes32 _sid, uint64 _L) internal pure returns (bytes32[] memory ys) {
        ys = new bytes32[](_L + 1);
        ys[_L] = keccak256("yL");
        for (uint64 idx = _L; idx > 0; idx--) {
            ys[idx - 1] = sha256(abi.encodePacked(_sid, idx - 1, ys[idx]));
        }
    }

    function uniqueCount(bytes32[] memory slots) internal pure returns (uint256 count) {
        bytes32[] memory seen = new bytes32[](slots.length);
        for (uint256 i = 0; i < slots.length; i++) {
            bool duplicate = false;
            for (uint256 j = 0; j < count; j++) {
                if (seen[j] == slots[i]) {
                    duplicate = true;
                    break;
                }
            }
            if (!duplicate) {
                seen[count] = slots[i];
                count++;
            }
        }
    }

    function sessionSlot(bytes32 _sid, uint256 offset) internal pure returns (bytes32) {
        bytes32 base = keccak256(abi.encode(_sid, uint256(0)));
        return bytes32(uint256(base) + offset);
    }

    function sessionNonZeroSlots(bytes32 _sid) internal view returns (uint256 count) {
        for (uint256 offset = 0; offset < 10; offset++) {
            if (vm.load(address(escrow), sessionSlot(_sid, offset)) != bytes32(0)) {
                count++;
            }
        }
    }

    function logAccessSummary(string memory label, address target) internal view {
        (bytes32[] memory reads, bytes32[] memory writes) = vm.accesses(target);
        console2.log(label);
        console2.log("  unique read slots", uniqueCount(reads));
        console2.log("  unique write slots", uniqueCount(writes));
    }

    function testStorageReport() public {
        bytes32[] memory ys = buildChain(sid, L);
        uint64 expB = uint64(block.timestamp + 1 days);

        vm.record();
        vm.prank(issuerB);
        token.approve(address(escrow), deposit);
        logAccessSummary("approve()", address(token));
        vm.stopRecord();

        vm.record();
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
        logAccessSummary("openSession() / Escrow", address(escrow));
        logAccessSummary("openSession() / MockERC20", address(token));
        console2.log("  retained nonzero session slots", sessionNonZeroSlots(sid));
        console2.log("  retained session bytes (approx)", sessionNonZeroSlots(sid) * 32);
        vm.stopRecord();

        vm.record();
        vm.prank(bm);
        escrow.claim(sid, 3, ys[3]);
        logAccessSummary("claim(i=3) / Escrow", address(escrow));
        logAccessSummary("claim(i=3) / MockERC20", address(token));
        console2.log("  retained nonzero session slots", sessionNonZeroSlots(sid));
        console2.log("  retained session bytes (approx)", sessionNonZeroSlots(sid) * 32);
        vm.stopRecord();

        vm.warp(uint256(expB) + 1);

        vm.record();
        vm.prank(issuerB);
        escrow.closeSession(sid);
        logAccessSummary("closeSession() / Escrow", address(escrow));
        logAccessSummary("closeSession() / MockERC20", address(token));
        console2.log("  retained nonzero session slots", sessionNonZeroSlots(sid));
        console2.log("  retained session bytes (approx)", sessionNonZeroSlots(sid) * 32);
        vm.stopRecord();
    }
}
