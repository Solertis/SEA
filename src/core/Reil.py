"""
   Copyright (c) 2013 neuromancer
   All rights reserved.
   
   Redistribution and use in source and binary forms, with or without
   modification, are permitted provided that the following conditions
   are met:
   1. Redistributions of source code must retain the above copyright
      notice, this list of conditions and the following disclaimer.
   2. Redistributions in binary form must reproduce the above copyright
      notice, this list of conditions and the following disclaimer in the
      documentation and/or other materials provided with the distribution.
   3. The name of the author may not be used to endorse or promote products
      derived from this software without specific prior written permission.

   THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
   IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
   OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
   IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT,
   INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
   NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
   DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
   THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
   (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF
   THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

from pkgs.pyparsing import Word, Literal, alphas, alphanums, delimitedList
from Types import *
from Operand import *
from Instruction import Instruction

address         = Word( alphanums).setResultsName("address")
colon           = Literal( ":" )
instruction     = Word( alphas ).setResultsName("instruction")
left_sbracket   = Literal("[")
right_sbracket  = Literal("]")
operand         = Word( alphanums+"-_" ).setResultsName("operand")
size            = Word( alphas ).setResultsName("size")
no_operand      = Literal( "EMPTY" ).setResultsName("operand") 

aug_operand = (size + operand) | no_operand

comma           = Literal(",")
body            = aug_operand + comma + aug_operand + comma + aug_operand
body            = body.setResultsName("augmented_operands")

reil = address + colon + instruction + left_sbracket + body + right_sbracket

# Quick detection of operand
def RegImmNoOp((name,size)):
  
  if name == "EMPTY":
    return NoOp(name,size)
  
  try:
    y = int(name)
    return ImmOp(name,size)
  except ValueError:
    return RegOp(name,size)

class REILInstruction(Instruction):
  def __init__(self, raw_ins):
    
    pins = reil.parseString(raw_ins)
    self.address = pins.address
    self.instruction = pins.instruction
    self.branchs = []
    self.branch_taken = None
    self.counter = None
    self.operands = []
    
    # for memory instructions
    self.mem_reg = None
    
    # for call instructions
    self.called_function = None
    
    aopers = pins.augmented_operands
    for (i,x) in enumerate(aopers):
       if x == ",":
        self.operands.append((aopers[i-1], aopers[i-2]))
    self.operands.append((aopers[-1], aopers[-2]))
    
    self.read_operands = []
    self.write_operands = []
    
    # ldm: op_2 = [op_0]
    if (pins.instruction == "ldm"):
      
      
      self.write_operands = [RegImmNoOp(self.operands[2])]
      
      name, size = self.operands[0]
      t = RegImmNoOp((name,size))
      
      if (t |iss| ImmOp):
        self.mem_reg = AddrOp(name, size)
        #self.read_operands = [pAddrOp(name, size)]
      elif (t |iss| RegOp):
        self.mem_reg = RegOp(name, size)
        #self.read_operands = [pRegOp(name, size)]
      else:
        assert(False)
      
      #self.operands = map(RegImmNoOp, self.operands)
      
    # stm: [op_2] = op_0
    elif (pins.instruction == "stm"):
      
      self.read_operands.append(RegImmNoOp(self.operands[0]))
      name, size = self.operands[2]
      t = RegImmNoOp((name,size))
      
      if (t |iss| ImmOp):
        self.mem_reg = AddrOp(name, size)
        #self.write_operands = [pAddrOp(name, size)]
      elif (t |iss| RegOp):
        self.mem_reg = RegOp(name, size)
        #self.write_operands = [pRegOp(name, size)]
      else:
        assert(False)

      
    elif (pins.instruction == "jcc"):
      
      
      #pass
      self.operands = map(RegImmNoOp, self.operands)
      self.read_operands  = filter(lambda o: not (o |iss| NoOp), self.operands[0:3])
      addr_size = "DWORD"      
      #print self.address, self.read_operands[0], self.read_operands[0].__class__ 
      
      if ( self.read_operands[-1] |iss| ImmOp): # jmp to a constant address

        self.branchs = [self.__mkReilAddr__(self.read_operands[-1])]

        #if (self.read_operands[0] |iss| ImmOp):
        #  pass

      self.write_operands = []

      if len(self.read_operands) == 3:
        self.setBranchTaken(self.read_operands[1].getValue())
	return
      
    elif (pins.instruction == "call"):
      
      if (self.operands[0][0] <> "EMPTY"):
         self.called_function = self.operands[0][0]
      
    else:
      
      self.operands = map(RegImmNoOp, self.operands)
      
      self.read_operands  = filter(lambda o: not (o |iss| NoOp), self.operands[0:2])
      self.write_operands = filter(lambda o: not (o |iss| NoOp), self.operands[2:3])
      
    
    if self.instruction in ["call", "ret", "bisz", "bsh", "stm", "ldm", "jcc"]:
      pass
    else:
      self.fixOperandSizes()
      
  def fixOperandSizes(self):
    
    #print self.instruction 
    write_sizes = map(lambda o: o.size, self.write_operands)
    read_sizes = map(lambda o: o.size, self.read_operands)
    
    size = min(min(write_sizes), min(read_sizes))
    assert(size > 0)
    
    #print "corrected size:", size
    
    for o in self.write_operands:
      o.resize(size)
   
    for o in self.read_operands:
      o.resize(size)
   
  def setMemoryAccess(self, mem_access):
    assert(mem_access <> None)
    
    ptype, offset = mem_access["access"]
    sname = getMemInfo(ptype)#, ptype.einfo["offset"]
    
    # ldm: op_2 = [op_0]
    if (self.instruction == "ldm"):

      write_operand = RegImmNoOp(self.operands[2])
      
      assert(write_operand |iss| RegOp)
      
      name = sname#+"@"+str(offset)
      op = MemOp(name, write_operand.getSizeInBits(), offset=offset)
      op.type = ptype
      #print "hola:", str(ptype)
      
      self.read_operands = [op]
      
    # stm: [op_2] = op_0
    elif (self.instruction == "stm"):

      read_operand = RegImmNoOp(self.operands[0])
      
      name = sname#+"@"+str(offset)
      op = MemOp(name, read_operand.getSizeInBits(), offset=offset)
      op.type = ptype
      
      #print "hola:", str(ptype)
      
      self.write_operands = [op]
      
    else:
      assert(False)

  def setBranchTaken(self, branch):
    assert(self.isCJmp())
    self.branch_taken = str(branch)

  def getBranchTaken(self):
    return str(self.branch_taken)        

  def __mkReilAddr__(self, op):
    addr_size = "DWORD"
    name = hex(op.getValue())+"00"
    return AddrOp(name,addr_size)

  def clearMemRegs(self):
    self.read_operands = filter(lambda op: op <> self.mem_reg, self.read_operands)
    #self.write_operands = filter(lambda op: op <> mem_reg, self.read_operads)
  
  def isCall(self):
    return self.instruction == "call"
  def isRet(self):
    return self.instruction == "ret"
    
  def __str__(self):

    if self.isCall() and self.called_function <> None:
      r = self.instruction + " "+ self.called_function
      return r


    r = self.instruction + "-> "
    for op in self.read_operands:
      r = r + str(op) + ", "
    
    r = r + "| "
    
    for op in self.write_operands:
      r = r + str(op) + ", "
    
    return r
  
  def isJmp(self):
    return self.instruction == "jcc" and (self.read_operands[0] |iss| ImmOp)
    
  def isCJmp(self):
    return self.instruction == "jcc" and not (self.read_operands[0] |iss| ImmOp)
 
def ReilParser(filename):
    openf = open(filename)
    r = []
    for raw_ins in openf.readlines():
      if not (raw_ins[0] == "#"):
        # TODO: create REILLabel class
        pins = reil.parseString(raw_ins)
        label = hex(int(pins.address,16)).replace("L","")
        addr_op = AddrOp(label, size)
      
        if (r <> []):
          if r[-1].isCJmp(): # if last was conditional jmp
            assert(r[-1].branchs <> [])
            r[-1].branchs.append(addr_op) # next instruction is the missing label in branchs

        r.append(addr_op)
        r.append(REILInstruction(raw_ins))
    
    return r
