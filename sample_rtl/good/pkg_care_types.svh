// ---------------------------------------------------------------------------
// Package : pkg_care_types
// Description : Shared type definitions and constants (SystemVerilog header)
// ---------------------------------------------------------------------------
`ifndef PKG_CARE_TYPES_SVH
`define PKG_CARE_TYPES_SVH

package pkg_care_types;

    // ── Data widths ─────────────────────────────────────
    localparam int DATA_WIDTH  = 32;
    localparam int ADDR_WIDTH  = 16;
    localparam int OPCODE_WIDTH = 4;

    // ── Opcodes ─────────────────────────────────────────
    typedef enum logic [OPCODE_WIDTH-1:0] {
        OP_NOP   = 4'h0,
        OP_LOAD  = 4'h1,
        OP_STORE = 4'h2,
        OP_ADD   = 4'h3,
        OP_SUB   = 4'h4,
        OP_AND   = 4'h5,
        OP_OR    = 4'h6,
        OP_XOR   = 4'h7,
        OP_SHL   = 4'h8,
        OP_SHR   = 4'h9,
        OP_BEQ   = 4'hA,
        OP_BNE   = 4'hB,
        OP_JMP   = 4'hC,
        OP_HALT  = 4'hF
    } opcode_t;

    // ── Bus transaction types ───────────────────────────
    typedef enum logic [1:0] {
        TXN_IDLE  = 2'b00,
        TXN_READ  = 2'b01,
        TXN_WRITE = 2'b10,
        TXN_BURST = 2'b11
    } txn_type_t;

    // ── AXI-lite response codes ─────────────────────────
    typedef enum logic [1:0] {
        RESP_OKAY   = 2'b00,
        RESP_EXOKAY = 2'b01,
        RESP_SLVERR = 2'b10,
        RESP_DECERR = 2'b11
    } axi_resp_t;

endpackage

`endif // PKG_CARE_TYPES_SVH
