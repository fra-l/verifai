// Simple 8-bit ALU for UVM-AI demonstration
module simple_alu (
  input  logic        clk,
  input  logic        rst_n,
  input  logic [1:0]  opcode,
  input  logic [7:0]  operand_a,
  input  logic [7:0]  operand_b,
  input  logic        valid_in,
  output logic [7:0]  result,
  output logic        valid_out,
  output logic        carry
);

  // Operation encoding
  localparam OP_ADD = 2'b00;
  localparam OP_SUB = 2'b01;
  localparam OP_AND = 2'b10;
  localparam OP_OR  = 2'b11;

  logic [8:0] alu_result;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      result    <= 8'h0;
      valid_out <= 1'b0;
      carry     <= 1'b0;
    end else if (valid_in) begin
      case (opcode)
        OP_ADD: alu_result = {1'b0, operand_a} + {1'b0, operand_b};
        OP_SUB: alu_result = {1'b0, operand_a} - {1'b0, operand_b};
        OP_AND: alu_result = {1'b0, operand_a & operand_b};
        OP_OR:  alu_result = {1'b0, operand_a | operand_b};
      endcase
      result    <= alu_result[7:0];
      carry     <= alu_result[8];
      valid_out <= 1'b1;
    end else begin
      valid_out <= 1'b0;
    end
  end

endmodule
