#pragma once
#include <stdint.h>
#include <stddef.h>
#include <math.h>
namespace lord_sumi {
enum class Quality { Valid, Missing, OutOfRange, Invalid, Fault };
struct QualitySnapshot { uint32_t accepted, rejected, missing; bool fault; };
class NumericQualityGate {
 public:
  NumericQualityGate(double low,double high):lo_(low),hi_(high),s_{0,0,0,false}{
    if(!isfinite(lo_)||!isfinite(hi_)||lo_>hi_) s_.fault=true;
  }
  Quality inspect(const char* input) {
    if(s_.fault) return Quality::Fault;
    if(s_.accepted==UINT32_MAX||s_.rejected==UINT32_MAX||s_.missing==UINT32_MAX){s_.fault=true;return Quality::Fault;}
    if(!input||!*input){++s_.missing;++s_.rejected;return Quality::Missing;}
    size_t n=0;bool dot=false;bool digit=false;
    if(input[0]=='+'||input[0]=='-') ++n;
    for(;input[n];++n) {
      if(n>=32){++s_.rejected;return Quality::Invalid;}
      if(input[n]=='.'&&!dot){dot=true;continue;}
      if(input[n]>='0'&&input[n]<='9'){digit=true;continue;}
      ++s_.rejected;return Quality::Invalid;
    }
    if(!digit){++s_.rejected;return Quality::Invalid;}
    double v=0.0;double fraction=0.1;bool after=false;bool neg=input[0]=='-';
    for(size_t i=(input[0]=='+'||input[0]=='-')?1:0;i<n;++i){
      if(input[i]=='.'){after=true;continue;}
      int d=input[i]-'0';
      if(after){v+=d*fraction;fraction*=0.1;}else{v=v*10+d;}
      if(!isfinite(v)){++s_.rejected;return Quality::Invalid;}
    }
    if(neg)v=-v;
    if(v<lo_||v>hi_){++s_.rejected;return Quality::OutOfRange;}
    ++s_.accepted;return Quality::Valid;
  }
  QualitySnapshot snapshot()const{return s_;}
 private: double lo_,hi_;QualitySnapshot s_;
};
}