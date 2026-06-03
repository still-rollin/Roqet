(** * Group and ring morphisms. A small demo slice of Mathematical Components. *)

(** A group homomorphism maps the identity to the identity. *)
Lemma morph1 : forall (gT rT : group) (f : {morphism gT >-> rT}), f 1 = 1.
Proof. Admitted.

(** A group homomorphism commutes with the inverse. *)
Lemma morphV : forall (gT rT : group) (f : {morphism gT >-> rT}) x,
  f (x^-1) = (f x)^-1.
Proof. Admitted.

(** A group homomorphism commutes with the group operation. *)
Lemma morphM : forall (gT rT : group) (f : {morphism gT >-> rT}) x y,
  f (x * y) = f x * f y.
Proof. Admitted.

(** The kernel of a group homomorphism is a normal subgroup. *)
Definition ker : forall (gT rT : group) (f : {morphism gT >-> rT}), {set gT}.
Proof. Admitted.
