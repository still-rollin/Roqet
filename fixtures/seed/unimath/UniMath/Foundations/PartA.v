(** * Foundations. A small demo slice of the UniMath library. *)

(** A type is a proposition when all its elements are equal. *)
Definition isaprop : forall (X : UU), UU.
Proof. Admitted.

(** A type has decidable equality when equality of any two elements is decidable. *)
Definition isdeceq : forall (X : UU), UU.
Proof. Admitted.

(** Function extensionality for dependent functions in UniMath. *)
Definition funextsec : forall (X : UU) (P : X -> UU) (f g : forall x, P x),
  (forall x, f x = g x) -> f = g.
Proof. Admitted.

(** The total space of a family of contractible types is equivalent to the base. *)
Lemma weqtotal2overunit : forall (P : unit -> UU), (total2 P) ≃ (P tt).
Proof. Admitted.
