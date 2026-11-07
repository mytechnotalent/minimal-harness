---
name: riscv-assembly-standard
description: "Use when writing, editing, or reviewing RISC-V assembly. Enforces the RP2350 driver style: file headers, section order, Doxygen comment blocks, aligned instructions, commented branches, and ABI discipline."
---

# RISC-V assembly standard

Reference: https://github.com/mytechnotalent/RP2350_Button_Driver_RISCV

These rules are mandatory.

## File header

Every `.s` file opens with a block comment containing `FILE`, `DESCRIPTION`,
`BRIEF`, `AUTHOR`, `CREATION DATE`, and `UPDATE DATE`. Use the project author,
not a copied name.

```asm
/**
 * FILE: main.s
 *
 * DESCRIPTION:
 * <what the file does>
 *
 * BRIEF:
 * <concise summary>
 *
 * AUTHOR: <PROJECT AUTHOR>
 * CREATION DATE: <DATE>
 * UPDATE DATE: <DATE>
 */
```

## Sections

Use shared constants through `.include "constants.s"`. Emit sections in this
order, each with a short comment:

```asm
.section .text                                   # code section
.align 2                                         # 4-byte alignment
.section .rodata                                 # read-only data
.section .data                                   # initialized data
.section .bss                                    # uninitialized data
```

## Functions and labels

- Document every function with `@brief`, `@details`, `@param`, and `@retval`.
- Export functions with `.global <name>` and `.type <name>, @function`.
- Name public routines `Module_Action` and local labels `.Loop`, `.Done`.
- End functions with `ret`.

```asm
/**
 * @brief   Initialize the driver.
 *
 * @details Configures the hardware for the main loop.
 *
 * @param   None
 * @retval  None
 */
.global Driver_Init                              # export Driver_Init
.type Driver_Init, @function                     # mark as function
Driver_Init:
.Loop:
  li    a0, 16                                   # load GPIO number
  call  GPIO_Set                                 # turn on the LED
  j     .Loop                                    # loop forever
  ret                                            # return to caller
```

## Instruction layout

- Indent instructions by two spaces.
- Align mnemonics and operands so inline comments line up.
- Use a `#` comment on every load, call, and branch.
- Keep the ABI: arguments in `a0`-`a7`, return in `a0`, preserve `s0`-`s11`.
- Do not use tabs. Keep lines within 79 columns when practical.
- Add a host or on-target test harness that exercises every public routine.
  Document hardware-only tests and the command that runs them. A routine
  without a test is incomplete.

## Verify

Assemble and link with the project toolchain. Zero warnings and a successful
build are required before the change is complete.
