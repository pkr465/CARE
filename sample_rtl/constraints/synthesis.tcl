# =============================================================================
# CARE Sample TCL — Synthesis Directives for sample_rtl
# =============================================================================

# Target library settings
set target_library "typical_1v0.db"
set link_library "* typical_1v0.db"

# Don't touch critical synchronizer cells
set_dont_touch [get_cells sync_reg]
set_dont_touch [get_cells gray_counter]

# Max fanout constraints
set_max_fanout 16 [get_ports clk]
set_max_fanout 8 [get_ports rst_n]

# Synthesis attributes
set_attribute [get_cells fifo_inst] keep true
set_attribute [get_cells alu_inst] dont_touch true

# Clock gating
set clock_gating_enable true
