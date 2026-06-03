(** * Functional extensionality. A small demo slice of the Rocq standard library. *)

(** Functional extensionality: two functions that agree on every input are equal. *)
Axiom functional_extensionality :
  forall (A B : Type) (f g : A -> B), (forall x, f x = g x) -> f = g.

(** Dependent functional extensionality. *)
Axiom functional_extensionality_dep :
  forall (A : Type) (B : A -> Type) (f g : forall a, B a),
    (forall x, f x = g x) -> f = g.

(** Proof irrelevance for propositions. *)
Axiom proof_irrelevance : forall (P : Prop) (p q : P), p = q.
